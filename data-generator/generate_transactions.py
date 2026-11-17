#!/usr/bin/env python3
"""
Générateur de données FICTIVES pour le projet « Banque Horizon ».

Produit :
  - des référentiels (instruments, clients)
  - des fichiers de transactions quotidiens (un fichier par jour)
  - volontairement « sales » : doublons, valeurs manquantes, formats de date
    mélangés, quantités négatives, instruments inconnus
  - optionnel : une dérive de schéma (colonne renommée / ajoutée)

Aucune donnée réelle n'est utilisée. Tout est généré aléatoirement.

Exemples :
  python generate_transactions.py --start 2026-01-05 --days 5 --out ./output
  python generate_transactions.py --start 2026-01-12 --days 1 --schema-drift --out ./output
"""
import argparse
import json
from datetime import date, datetime, timedelta, time
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

DESKS = ["EQUITIES", "FX", "RATES", "CREDIT", "COMMODITIES"]
ASSET_CLASS = {
    "EQUITIES": "Equity",
    "FX": "FX",
    "RATES": "Bond",
    "CREDIT": "Corporate bond",
    "COMMODITIES": "Commodity",
}
CURRENCIES = ["EUR", "USD", "GBP", "CHF"]
SEGMENTS = ["Hedge fund", "Asset manager", "Corporate", "Pension fund"]
COUNTRIES = ["FR", "DE", "GB", "US", "CH", "LU", "NL", "IT"]


def make_instruments(fake: Faker, rng: np.random.Generator, n: int = 40) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        desk = DESKS[(i - 1) % len(DESKS)]
        rows.append(
            {
                "instrument_id": f"INS{i:04d}",
                "instrument_name": fake.company(),
                "isin": fake.bothify("??#########?").upper(),  # format ISIN-like, NON valide
                "desk": desk,
                "asset_class": ASSET_CLASS[desk],
                "currency": str(rng.choice(CURRENCIES)),
                "ref_price": round(float(rng.uniform(10, 500)), 2),
            }
        )
    return pd.DataFrame(rows)


def make_clients(fake: Faker, rng: np.random.Generator, n: int = 200, dirty: bool = True) -> pd.DataFrame:
    rows = []
    for i in range(1, n + 1):
        rows.append(
            {
                "client_id": f"CLI{i:05d}",
                "client_name": fake.company(),
                "country": str(rng.choice(COUNTRIES)),
                "segment": str(rng.choice(SEGMENTS)),
                "risk_rating": int(rng.integers(1, 6)),
                "created_at": fake.date_between(start_date="-8y", end_date="-1y").isoformat(),
            }
        )
    df = pd.DataFrame(rows)
    if dirty:
        # Doublons « métier » : même client, nom légèrement différent, autre identifiant
        dups = df.sample(frac=0.03, random_state=1).copy()
        dups["client_id"] = [f"CLI{n + k + 1:05d}" for k in range(len(dups))]
        dups["client_name"] = dups["client_name"].str.upper() + " "
        df = pd.concat([df, dups], ignore_index=True)
    return df


def make_transactions(day: date, n: int, instruments: pd.DataFrame, clients: pd.DataFrame,
                      rng: np.random.Generator, dirty_rate: float, schema_drift: bool):
    ins = instruments.sample(n, replace=True, random_state=int(rng.integers(0, 1_000_000))).reset_index(drop=True)
    valid_clients = clients["client_id"].tolist()
    start = datetime.combine(day, time(7, 0))

    df = pd.DataFrame(
        {
            "transaction_id": [f"TRX{day:%Y%m%d}{i:06d}" for i in range(n)],
            "trade_timestamp": [
                (start + timedelta(seconds=int(s))).strftime("%Y-%m-%d %H:%M:%S")
                for s in rng.integers(0, 10 * 3600, n)
            ],
            "trade_date": day.isoformat(),
            "desk": ins["desk"],
            "trader_id": [f"TRD{int(t):03d}" for t in rng.integers(1, 30, n)],
            "client_id": rng.choice(valid_clients, n),
            "instrument_id": ins["instrument_id"],
            "side": rng.choice(["BUY", "SELL"], n),
            "quantity": rng.integers(1, 5000, n),
            "price": (ins["ref_price"] * (1 + rng.normal(0, 0.02, n))).round(4),
            "currency": ins["currency"],
            "status": rng.choice(["EXECUTED", "EXECUTED", "EXECUTED", "CANCELLED"], n),
            "source_system": "TRADING_APP_01",
        }
    )
    df["notional"] = (df["quantity"] * df["price"]).round(2)

    issues = {"date": day.isoformat(), "rows_clean": n}
    k = max(1, int(n * dirty_rate))

    if dirty_rate > 0:
        # 1) client manquant
        idx = df.sample(k, random_state=1).index
        df.loc[idx, "client_id"] = None
        issues["missing_client_id"] = len(idx)

        # 2) quantité négative
        idx = df.sample(k, random_state=2).index
        df.loc[idx, "quantity"] = -df.loc[idx, "quantity"]
        issues["negative_quantity"] = len(idx)

        # 3) instrument inconnu du référentiel
        idx = df.sample(k, random_state=3).index
        df.loc[idx, "instrument_id"] = "INS9999"
        issues["unknown_instrument"] = len(idx)

        # 4) formats de date mélangés
        idx = df.sample(k * 4, random_state=4).index
        df.loc[idx, "trade_date"] = day.strftime("%d/%m/%Y")
        issues["mixed_date_format"] = len(idx)

        # 5) doublons exacts (fichier envoyé avec des lignes en double)
        dups = df.sample(k, random_state=5)
        df = pd.concat([df, dups], ignore_index=True)
        issues["duplicate_rows"] = len(dups)

    if schema_drift:
        # Dérive de schéma : colonne renommée + nouvelle colonne
        df = df.rename(columns={"quantity": "qty"})
        df["venue"] = "XPAR"
        issues["schema_drift"] = "quantity -> qty ; new column venue"

    issues["rows_total"] = len(df)
    return df, issues


def main():
    p = argparse.ArgumentParser(description="Générateur de données fictives Banque Horizon")
    p.add_argument("--start", default="2026-01-05", help="Premier jour (AAAA-MM-JJ)")
    p.add_argument("--days", type=int, default=5, help="Nombre de jours à générer")
    p.add_argument("--n", type=int, default=5000, help="Transactions par jour (avant doublons)")
    p.add_argument("--dirty-rate", type=float, default=0.01, help="Part de lignes défectueuses (0 = données propres)")
    p.add_argument("--schema-drift", action="store_true", help="Simule un changement de schéma")
    p.add_argument("--seed", type=int, default=42, help="Graine aléatoire (reproductibilité)")
    p.add_argument("--out", default="./output", help="Dossier de sortie")
    args = p.parse_args()

    rng = np.random.default_rng(args.seed)
    fake = Faker("fr_FR")
    Faker.seed(args.seed)

    out = Path(args.out)
    (out / "referentiel").mkdir(parents=True, exist_ok=True)
    (out / "transactions").mkdir(parents=True, exist_ok=True)
    (out / "_controle").mkdir(parents=True, exist_ok=True)

    instruments = make_instruments(fake, rng)
    clients = make_clients(fake, rng, dirty=args.dirty_rate > 0)
    instruments.to_csv(out / "referentiel" / "instruments.csv", index=False)
    clients.to_csv(out / "referentiel" / "clients.csv", index=False)

    day = date.fromisoformat(args.start)
    for _ in range(args.days):
        df, issues = make_transactions(day, args.n, instruments, clients, rng,
                                       args.dirty_rate, args.schema_drift)
        df.to_csv(out / "transactions" / f"transactions_{day:%Y%m%d}.csv", index=False)
        # Fichier de contrôle : sert à vérifier que TES contrôles qualité détectent bien les anomalies.
        # Ne le charge PAS dans le lakehouse.
        (out / "_controle" / f"issues_{day:%Y%m%d}.json").write_text(json.dumps(issues, indent=2, ensure_ascii=False))
        print(f"{day} : {issues['rows_total']} lignes")
        day += timedelta(days=1)

    print(f"\nTerminé. Fichiers dans : {out.resolve()}")


if __name__ == "__main__":
    main()
