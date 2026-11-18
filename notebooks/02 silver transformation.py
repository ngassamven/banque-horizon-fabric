# =====================================================================
# Banque Horizon - Notebook 02 : couche Silver
# A coller dans un notebook Fabric (PySpark), Lakehouse lh_horizon par défaut.
# Chaque bloc "# CELL" = une cellule.
#
# Silver = donnée TYPÉE, DÉDOUBLONNÉE, CONTRÔLÉE.
#  - lignes valides      -> silver_transactions
#  - lignes rejetées     -> silver_rejects (avec le motif, rien n'est perdu)
#  - mesures qualité     -> ops_quality_metrics
# =====================================================================

# CELL 1 - PARAMETRES (cellule de paramètres : "Toggle parameter cell")
run_date = "2026-01-05"      # jour Bronze à traiter (AAAA-MM-JJ)
max_reject_rate = 0.05       # au-delà : statut SUCCESS_WITH_WARNINGS
fail_on_threshold = False    # True : le notebook échoue si le seuil est dépassé

# CELL 2 - IMPORTS, CONSTANTES, REGLES
import uuid
from datetime import datetime, timezone
from pyspark.sql import functions as F, Window
from pyspark.sql.types import (StructType, StructField, StringType,
                               LongType, TimestampType)

silver_batch_id = f"S{run_date.replace('-', '')}-{uuid.uuid4().hex[:8]}"
started_at = datetime.now(timezone.utc)

RAW_COLS = ["transaction_id", "trade_timestamp", "trade_date", "desk", "trader_id",
            "client_id", "instrument_id", "side", "quantity", "price", "currency",
            "status", "source_system", "notional"]

# Décision INC-001 : en Silver, on réconcilie les colonnes renommées par la source.
COLUMN_ALIASES = {"qty": "quantity"}

VALID_SIDES = ["BUY", "SELL"]

# code de règle -> (description, traitement)
RULES = {
    "R01_ID_MISSING":       ("transaction_id absent", "REJECT"),
    "R02_CLIENT_MISSING":   ("client_id absent", "REJECT"),
    "R03_CLIENT_UNKNOWN":   ("client_id absent du référentiel clients", "REJECT"),
    "R04_QTY_INVALID":      ("quantité absente, non numérique ou <= 0", "REJECT"),
    "R05_INSTRUMENT_UNKNOWN": ("instrument absent du référentiel", "REJECT"),
    "R06_DATE_INVALID":     ("trade_date illisible", "REJECT"),
    "R07_PRICE_INVALID":    ("prix absent, non numérique ou <= 0", "REJECT"),
    "R08_SIDE_INVALID":     ("sens différent de BUY / SELL", "REJECT"),
    "DUPLICATE_REMOVED":    ("doublon exact sur transaction_id supprimé", "INFO"),
    "DATE_FORMAT_NORMALIZED": ("date JJ/MM/AAAA convertie en date", "INFO"),
    "SCHEMA_ALIAS_USED":    ("valeur reprise d'une colonne renommée (qty)", "INFO"),
}

LOG_SCHEMA = StructType([
    StructField("batch_id", StringType()), StructField("target_table", StringType()),
    StructField("source", StringType()), StructField("rows_read", LongType()),
    StructField("rows_in_table", LongType()), StructField("status", StringType()),
    StructField("message", StringType()), StructField("started_at", TimestampType()),
    StructField("ended_at", TimestampType()),
])

METRICS_SCHEMA = StructType([
    StructField("silver_batch_id", StringType()), StructField("run_date", StringType()),
    StructField("rule", StringType()), StructField("description", StringType()),
    StructField("treatment", StringType()), StructField("rows_affected", LongType()),
    StructField("processed_at", TimestampType()),
])

# CELL 3 - FONCTIONS
def blank(c):
    """Vrai si la colonne est nulle ou vide."""
    return F.col(c).isNull() | (F.trim(F.col(c)) == "")

def harmonize_columns(df):
    """Dérive de schéma : applique les alias, ajoute les colonnes absentes (null)."""
    df = df.withColumn("_alias_used", F.lit(False))
    for alias, target in COLUMN_ALIASES.items():
        if alias in df.columns:
            if target not in df.columns:
                df = df.withColumn(target, F.lit(None).cast("string"))
            df = (df.withColumn("_alias_used",
                                F.col("_alias_used") | (F.col(target).isNull() & F.col(alias).isNotNull()))
                    .withColumn(target, F.coalesce(F.col(target), F.col(alias))))
    for c in RAW_COLS:
        if c not in df.columns:
            df = df.withColumn(c, F.lit(None).cast("string"))
    return df

def parse_types(df):
    """Conversion texte -> types. Une valeur illisible devient NULL (jamais d'exception),
    et c'est ensuite une règle qui la rejette."""
    t = lambda c: F.trim(F.col(c))
    is_iso = t("trade_date").rlike(r"^\d{4}-\d{2}-\d{2}$")
    is_fr = t("trade_date").rlike(r"^\d{2}/\d{2}/\d{4}$")
    num = r"^-?\d+(\.\d+)?$"
    return (df
        .withColumn("_date_was_fr", is_fr)
        .withColumn("trade_date_p",
                    F.when(is_iso, F.to_date(t("trade_date"), "yyyy-MM-dd"))
                     .when(is_fr, F.to_date(t("trade_date"), "dd/MM/yyyy")))
        .withColumn("trade_timestamp_p",
                    F.when(t("trade_timestamp").rlike(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"),
                           F.to_timestamp(t("trade_timestamp"), "yyyy-MM-dd HH:mm:ss")))
        .withColumn("quantity_p", F.when(t("quantity").rlike(r"^-?\d+$"), t("quantity").cast("int")))
        .withColumn("price_p", F.when(t("price").rlike(num), t("price").cast("decimal(18,4)")))
        .withColumn("notional_p", F.when(t("notional").rlike(num), t("notional").cast("decimal(18,2)"))))

def deduplicate(df):
    """Garde une ligne par transaction_id. Les lignes sans identifiant ne sont jamais
    regroupées entre elles (elles seront rejetées par R01)."""
    key = (F.when(blank("transaction_id"),
                  F.concat(F.lit("NOID_"), F.monotonically_increasing_id().cast("string")))
            .otherwise(F.trim(F.col("transaction_id"))))
    w = Window.partitionBy(key).orderBy(F.col("_loaded_at"), F.col("_source_file"))
    return (df.withColumn("_rn", F.row_number().over(w))
              .where(F.col("_rn") == 1).drop("_rn"))

def apply_rules(df, instruments, clients):
    """Ajoute la colonne reject_reasons (tableau des règles enfreintes)."""
    inst = (instruments.select(F.trim(F.col("instrument_id")).alias("_i_id")).distinct()
                       .withColumn("_inst_ok", F.lit(True)))
    cli = (clients.select(F.trim(F.col("client_id")).alias("_c_id")).distinct()
                  .withColumn("_cli_ok", F.lit(True)))
    df = (df.join(F.broadcast(inst), F.trim(F.col("instrument_id")) == F.col("_i_id"), "left")
            .join(F.broadcast(cli), F.trim(F.col("client_id")) == F.col("_c_id"), "left"))
    side_ok = F.coalesce(F.upper(F.trim(F.col("side"))).isin(*VALID_SIDES), F.lit(False))
    conds = [
        ("R01_ID_MISSING", blank("transaction_id")),
        ("R02_CLIENT_MISSING", blank("client_id")),
        ("R03_CLIENT_UNKNOWN", ~blank("client_id") & F.col("_cli_ok").isNull()),
        ("R04_QTY_INVALID", F.col("quantity_p").isNull() | (F.col("quantity_p") <= 0)),
        ("R05_INSTRUMENT_UNKNOWN", F.col("_inst_ok").isNull()),
        ("R06_DATE_INVALID", F.col("trade_date_p").isNull()),
        ("R07_PRICE_INVALID", F.col("price_p").isNull() | (F.col("price_p") <= 0)),
        ("R08_SIDE_INVALID", ~side_ok),
    ]
    arr = F.array(*[F.when(cond, F.lit(code)) for code, cond in conds])
    return (df.withColumn("reject_reasons", F.filter(arr, lambda x: x.isNotNull()))
              .drop("_i_id", "_inst_ok", "_c_id", "_cli_ok"))

def transform_transactions(bronze, instruments, clients):
    """Enchaîne : alias -> types -> dédoublonnage -> règles. Renvoie valides, rejetées, chiffres."""
    rows_bronze = bronze.count()
    kept = deduplicate(parse_types(harmonize_columns(bronze)))
    checked = apply_rules(kept, instruments, clients).cache()

    kept_n = checked.count()
    rejected = checked.where(F.size("reject_reasons") > 0)
    valid = checked.where(F.size("reject_reasons") == 0)
    rejected_n = rejected.count()
    valid_n = kept_n - rejected_n

    by_rule = {r["rule"]: r["n"] for r in
               checked.select(F.explode("reject_reasons").alias("rule"))
                      .groupBy("rule").agg(F.count("*").alias("n")).collect()}
    counts = {code: int(by_rule.get(code, 0)) for code, (_, tr) in RULES.items() if tr == "REJECT"}
    counts["DUPLICATE_REMOVED"] = rows_bronze - kept_n
    counts["DATE_FORMAT_NORMALIZED"] = checked.where(
        F.col("_date_was_fr") & F.col("trade_date_p").isNotNull()).count()
    counts["SCHEMA_ALIAS_USED"] = checked.where(F.col("_alias_used")).count()

    stats = {"rows_bronze": rows_bronze, "duplicates_removed": rows_bronze - kept_n,
             "unique_rows": kept_n, "valid": valid_n, "rejected": rejected_n, "rules": counts}
    return valid, rejected, stats

def to_silver(valid, silver_batch_id):
    return valid.select(
        F.trim("transaction_id").alias("transaction_id"),
        F.col("trade_timestamp_p").alias("trade_timestamp"),
        F.col("trade_date_p").alias("trade_date"),
        F.trim("desk").alias("desk"), F.trim("trader_id").alias("trader_id"),
        F.trim("client_id").alias("client_id"), F.trim("instrument_id").alias("instrument_id"),
        F.upper(F.trim("side")).alias("side"),
        F.col("quantity_p").alias("quantity"), F.col("price_p").alias("price"),
        F.upper(F.trim("currency")).alias("currency"), F.trim("status").alias("status"),
        F.col("notional_p").alias("notional"), F.trim("source_system").alias("source_system"),
        "_file_date", F.col("_batch_id").alias("_bronze_batch_id"), "_source_file",
        F.lit(silver_batch_id).alias("_silver_batch_id"),
        F.current_timestamp().alias("_processed_at"))

def to_rejects(rejected, silver_batch_id):
    return rejected.select(
        "transaction_id",
        F.concat_ws(";", "reject_reasons").alias("reject_reasons"),
        F.to_json(F.struct(*[F.col(c) for c in RAW_COLS])).alias("raw_record"),
        "_file_date", F.col("_batch_id").alias("_bronze_batch_id"), "_source_file",
        F.lit(silver_batch_id).alias("_silver_batch_id"),
        F.current_timestamp().alias("_processed_at"))

def write_replace(df, table, key_col, key_value):
    """Réécrit uniquement la tranche du jour : relancer ne crée pas de doublons."""
    if spark.catalog.tableExists(table):
        (df.write.format("delta").mode("overwrite")
           .option("replaceWhere", f"{key_col} = '{key_value}'")
           .option("mergeSchema", "true").saveAsTable(table))
    else:
        df.write.format("delta").mode("overwrite").saveAsTable(table)

def log_load(target_table, source, rows_read, rows_in_table, status, message=""):
    """Journal au mieux : ne masque jamais l'erreur d'origine."""
    row = (silver_batch_id, target_table, source, rows_read, rows_in_table, status,
           (message or "")[:500], started_at, datetime.now(timezone.utc))
    try:
        (spark.createDataFrame([row], LOG_SCHEMA).write.format("delta").mode("append")
              .option("mergeSchema", "true").saveAsTable("ops_load_log"))
        return True
    except Exception as log_err:
        print(f"ATTENTION : journal non écrit ({log_err})")
        print(f"Entrée de journal perdue : {row}")
        return False

# CELL 4 - REFERENTIELS SILVER (typés, doublons métier SIGNALÉS mais pas fusionnés)
# Fusionner deux clients est une décision métier : on signale, on ne décide pas.
# Clé de rapprochement : nom normalisé + pays + date de création. Le nom seul donne
# trop de faux positifs (des entreprises différentes peuvent porter le même nom).
try:
    b_cli = spark.table("bronze_clients")
    s_cli = (b_cli
        .withColumn("risk_rating", F.col("risk_rating").cast("int"))
        .withColumn("created_at", F.to_date(F.trim("created_at"), "yyyy-MM-dd"))
        .withColumn("client_name_norm",
                    F.upper(F.trim(F.regexp_replace("client_name", r"\s+", " "))))
        .withColumn("duplicate_group_size",
                    F.count("*").over(Window.partitionBy("client_name_norm", "country", "created_at")))
        .select("client_id", "client_name", "client_name_norm", "country", "segment",
                "risk_rating", "created_at", "duplicate_group_size",
                F.col("_batch_id").alias("_bronze_batch_id")))
    s_cli.write.format("delta").mode("overwrite").option("overwriteSchema", "true") \
         .saveAsTable("silver_clients")

    b_ins = spark.table("bronze_instruments")
    s_ins = (b_ins.withColumn("ref_price", F.col("ref_price").cast("decimal(18,2)"))
                  .select("instrument_id", "instrument_name", "isin", "desk", "asset_class",
                          "currency", "ref_price", F.col("_batch_id").alias("_bronze_batch_id")))
    s_ins.write.format("delta").mode("overwrite").option("overwriteSchema", "true") \
         .saveAsTable("silver_instruments")

    n_dup = spark.table("silver_clients").where("duplicate_group_size > 1").count()
    print(f"silver_clients : {spark.table('silver_clients').count()} lignes, "
          f"{n_dup} lignes dans un groupe de doublons potentiels")
    print(f"silver_instruments : {spark.table('silver_instruments').count()} lignes")
except Exception as e:
    log_load("silver_referentiels", "bronze_clients/bronze_instruments", None, None, "FAILED", str(e))
    raise

# CELL 5 - TRANSACTIONS SILVER POUR LE JOUR (idempotent)
try:
    bronze = spark.table("bronze_transactions").where(F.col("_file_date") == run_date)
    instruments = spark.table("silver_instruments")
    clients = spark.table("silver_clients")

    valid, rejected, stats = transform_transactions(bronze, instruments, clients)

    if stats["rows_bronze"] == 0:
        raise ValueError(f"Aucune ligne Bronze pour {run_date} : charger Bronze d'abord")

    # Rapprochement : rien ne doit disparaître sans explication
    accounted = stats["valid"] + stats["rejected"] + stats["duplicates_removed"]
    if accounted != stats["rows_bronze"]:
        raise ValueError(f"Rapprochement KO : Bronze {stats['rows_bronze']} lignes, "
                         f"expliquées {accounted}")

    s_valid = to_silver(valid, silver_batch_id)
    s_rej = to_rejects(rejected, silver_batch_id)
    write_replace(s_valid, "silver_transactions", "_file_date", run_date)
    write_replace(s_rej, "silver_rejects", "_file_date", run_date)

    metrics = [(silver_batch_id, run_date, code, desc, treat, int(stats["rules"].get(code, 0)),
                datetime.now(timezone.utc)) for code, (desc, treat) in RULES.items()]
    write_replace(spark.createDataFrame(metrics, METRICS_SCHEMA),
                  "ops_quality_metrics", "run_date", run_date)

    in_silver = spark.table("silver_transactions").where(F.col("_file_date") == run_date).count()
    reject_rate = stats["rejected"] / max(stats["unique_rows"], 1)
    warnings = []
    if in_silver != stats["valid"]:
        warnings.append(f"écart d'écriture : {stats['valid']} attendues, {in_silver} en table")
    if reject_rate > max_reject_rate:
        warnings.append(f"taux de rejet {reject_rate:.1%} > seuil {max_reject_rate:.0%}")
        if fail_on_threshold:
            raise ValueError(warnings[-1])

    log_load("silver_transactions", f"bronze_transactions[{run_date}]", stats["rows_bronze"],
             in_silver, "SUCCESS_WITH_WARNINGS" if warnings else "SUCCESS", " ; ".join(warnings))
    print(f"{run_date} : Bronze {stats['rows_bronze']} | doublons supprimés "
          f"{stats['duplicates_removed']} | valides {stats['valid']} | "
          f"rejetées {stats['rejected']} ({reject_rate:.1%})")
    for w in warnings:
        print("ATTENTION :", w)
except Exception as e:
    log_load("silver_transactions", f"bronze_transactions[{run_date}]", None, None, "FAILED", str(e))
    raise

# CELL 6 - CONTROLES (à lancer à la main)
spark.sql(f"""
    SELECT rule, treatment, rows_affected
    FROM ops_quality_metrics WHERE run_date = '{run_date}'
    ORDER BY treatment DESC, rule
""").show(truncate=False)

spark.sql("""
    SELECT _file_date, COUNT(*) AS lignes_valides
    FROM silver_transactions GROUP BY _file_date ORDER BY _file_date
""").show()

spark.sql("""
    SELECT _file_date, COUNT(*) AS lignes_rejetees
    FROM silver_rejects GROUP BY _file_date ORDER BY _file_date
""").show()
