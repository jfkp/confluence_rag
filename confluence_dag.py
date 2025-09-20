from airflow import DAG
from airflow.operators.bash import BashOperator
from datetime import datetime, timedelta

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="confluence_to_opensearch",
    default_args=default_args,
    description="Sync Confluence pages, comments, and attachments to OpenSearch",
    schedule_interval="@daily",   # adjust as needed
    start_date=datetime(2025, 1, 1),
    catchup=False,
) as dag:

    ingest = BashOperator(
        task_id="full_ingest",
        bash_command="python /app/confluence_ingest.py",
        env={
            "CONFLUENCE_BASE": "{{ var.value.CONFLUENCE_BASE }}",
            "CONFLUENCE_PAT": "{{ var.value.CONFLUENCE_PAT }}",
            "OPENAI_API_KEY": "{{ var.value.OPENAI_API_KEY }}",
            "OPENSEARCH_HOST": "{{ var.value.OPENSEARCH_HOST }}"
        }
    )

    sync = BashOperator(
        task_id="incremental_sync",
        bash_command="python /app/confluence_sync.py",
        env={
            "CONFLUENCE_BASE": "{{ var.value.CONFLUENCE_BASE }}",
            "CONFLUENCE_PAT": "{{ var.value.CONFLUENCE_PAT }}",
            "OPENAI_API_KEY": "{{ var.value.OPENAI_API_KEY }}",
            "OPENSEARCH_HOST": "{{ var.value.OPENSEARCH_HOST }}"
        }
    )

    ingest >> sync
