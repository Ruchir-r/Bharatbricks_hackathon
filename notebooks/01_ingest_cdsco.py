# Databricks notebook source
# MAGIC %md
# MAGIC # CDSCO → Delta ingestion
# MAGIC Loads pre-extracted CSVs (in repo `/data`) into Delta tables.
# MAGIC Run this once after `databricks bundle deploy`.

# COMMAND ----------
dbutils.widgets.text("catalog", "hack_cdsco")
dbutils.widgets.text("schema", "core")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"USE {catalog}.{schema}")

# COMMAND ----------
import os
DATA_DIR = "/Workspace" + os.path.dirname(os.getcwd()) + "/data"

def load_csv_to_delta(csv_name, table_name):
    path = f"{DATA_DIR}/{csv_name}"
    df = spark.read.option("header", True).option("multiLine", True).csv(path)
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table_name)
    print(f"{table_name}: {df.count()} rows")

# COMMAND ----------
load_csv_to_delta("cdsco_approved.csv", "cdsco_approved")
load_csv_to_delta("cdsco_banned.csv", "cdsco_banned")
load_csv_to_delta("cdsco_nsq_alerts.csv", "cdsco_nsq_alerts")
load_csv_to_delta("cdsco_fdc_approved.csv", "cdsco_fdc_approved")
load_csv_to_delta("pmbjp_prices.csv", "pmbjp_prices")
load_csv_to_delta("nlem_essential.csv", "nlem_essential")

# COMMAND ----------
# MAGIC %md
# MAGIC ### Empty operational tables (created here so app reads/writes them)

tables = {
    "patient_sessions": """(
        session_id STRING, patient_name STRING, phone STRING,
        preferred_language STRING, emergency_contact_phone STRING,
        created_at TIMESTAMP
    )""",
    "prescription_scans": """(
        scan_id STRING, session_id STRING, image_path STRING,
        extracted_drugs STRING, created_at TIMESTAMP
    )""",
    "drug_timetable": """(
        entry_id STRING, session_id STRING, drug_name STRING,
        dose STRING, times_of_day ARRAY<STRING>,
        duration_days INT, start_date DATE
    )""",
    "side_effect_log": """(
        log_id STRING, session_id STRING, drug_name STRING,
        symptom STRING, severity INT, logged_at TIMESTAMP
    )""",
    "reminder_calls": """(
        call_id STRING, session_id STRING, drug_name STRING,
        scheduled_for TIMESTAMP, twilio_sid STRING, status STRING
    )""",
    "sos_events": """(
        event_id STRING, session_id STRING, location STRING,
        triggered_at TIMESTAMP, contact_notified STRING
    )""",
    "inference_log": """(
        req_id STRING, session_id STRING, stage STRING,
        input STRING, output STRING, latency_ms INT, logged_at TIMESTAMP
    )""",
}
for t, ddl in tables.items():
    spark.sql(f"CREATE TABLE IF NOT EXISTS {t} {ddl} USING DELTA")
    print(f"ready: {t}")
