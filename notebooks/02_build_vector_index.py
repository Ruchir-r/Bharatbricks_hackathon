# Databricks notebook source
# MAGIC %md
# MAGIC # Vector Search index over approved-drug descriptions
# MAGIC Enables RAG for plain-language explanation pipeline.

# COMMAND ----------
dbutils.widgets.text("catalog", "hack_cdsco")
dbutils.widgets.text("schema", "core")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# COMMAND ----------
from databricks.vector_search.client import VectorSearchClient

vsc = VectorSearchClient()
ENDPOINT = "hack_cdsco_endpoint"
SOURCE = f"{catalog}.{schema}.cdsco_approved"
INDEX = f"{catalog}.{schema}.cdsco_approved_idx"

# Enable CDC so the index can track updates
spark.sql(f"ALTER TABLE {SOURCE} SET TBLPROPERTIES (delta.enableChangeDataFeed=true)")

try:
    vsc.create_endpoint(name=ENDPOINT, endpoint_type="STANDARD")
except Exception as e:
    print(f"endpoint exists or in progress: {e}")

try:
    vsc.create_delta_sync_index(
        endpoint_name=ENDPOINT,
        source_table_name=SOURCE,
        index_name=INDEX,
        pipeline_type="TRIGGERED",
        primary_key="drug_name",
        embedding_source_column="description",
        embedding_model_endpoint_name="databricks-gte-large-en",
    )
except Exception as e:
    print(f"index exists or in progress: {e}")

print(f"Index: {INDEX}")
