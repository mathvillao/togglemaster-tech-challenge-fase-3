import json
import logging
import os
import sys
import threading
import time
import uuid

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

AWS_REGION = os.getenv("AWS_REGION")
SQS_QUEUE_URL = os.getenv("AWS_SQS_URL")
DYNAMODB_TABLE_NAME = os.getenv("AWS_DYNAMODB_TABLE")
SQS_ENDPOINT_URL = os.getenv("AWS_SQS_ENDPOINT_URL")
DYNAMODB_ENDPOINT_URL = os.getenv("AWS_DYNAMODB_ENDPOINT_URL")
SQS_WORKER_ENABLED = os.getenv("SQS_WORKER_ENABLED", "true").lower() == "true"
CREATE_DYNAMODB_TABLE = os.getenv("CREATE_DYNAMODB_TABLE_IF_NOT_EXISTS", "false").lower() == "true"

if not all([AWS_REGION, DYNAMODB_TABLE_NAME]):
    log.critical("Erro: AWS_REGION e AWS_DYNAMODB_TABLE devem ser definidos.")
    sys.exit(1)

if SQS_WORKER_ENABLED and not SQS_QUEUE_URL:
    log.critical("Erro: AWS_SQS_URL deve ser definido quando SQS_WORKER_ENABLED=true.")
    sys.exit(1)

try:
    session = boto3.Session(region_name=AWS_REGION)
    sqs_client = session.client("sqs", endpoint_url=SQS_ENDPOINT_URL) if SQS_WORKER_ENABLED else None
    dynamodb_client = session.client("dynamodb", endpoint_url=DYNAMODB_ENDPOINT_URL)
    log.info("Clientes Boto3 inicializados na regiao %s", AWS_REGION)
except NoCredentialsError:
    log.critical("Credenciais da AWS nao encontradas. Verifique seu ambiente.")
    sys.exit(1)
except Exception as exc:
    log.critical("Erro ao inicializar o Boto3: %s", exc)
    sys.exit(1)


def ensure_dynamodb_table():
    """Create the local DynamoDB table when requested by docker compose."""
    if not CREATE_DYNAMODB_TABLE:
        return

    try:
        dynamodb_client.describe_table(TableName=DYNAMODB_TABLE_NAME)
        log.info("Tabela DynamoDB '%s' ja existe.", DYNAMODB_TABLE_NAME)
    except dynamodb_client.exceptions.ResourceNotFoundException:
        log.info("Criando tabela DynamoDB '%s'...", DYNAMODB_TABLE_NAME)
        dynamodb_client.create_table(
            TableName=DYNAMODB_TABLE_NAME,
            AttributeDefinitions=[
                {"AttributeName": "event_id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "event_id", "KeyType": "HASH"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        waiter = dynamodb_client.get_waiter("table_exists")
        waiter.wait(TableName=DYNAMODB_TABLE_NAME)
        log.info("Tabela DynamoDB '%s' criada com sucesso.", DYNAMODB_TABLE_NAME)
    except ClientError as exc:
        log.error("Erro ao verificar/criar tabela DynamoDB: %s", exc)
        raise


def process_message(message):
    """Process one SQS message and persist the analytics event in DynamoDB."""
    try:
        log.info("Processando mensagem ID: %s", message["MessageId"])
        body = json.loads(message["Body"])
        event_id = str(uuid.uuid4())

        item = {
            "event_id": {"S": event_id},
            "user_id": {"S": body["user_id"]},
            "flag_name": {"S": body["flag_name"]},
            "result": {"BOOL": body["result"]},
            "timestamp": {"S": body["timestamp"]},
        }

        dynamodb_client.put_item(TableName=DYNAMODB_TABLE_NAME, Item=item)
        log.info("Evento %s (Flag: %s) salvo no DynamoDB.", event_id, body["flag_name"])

        sqs_client.delete_message(
            QueueUrl=SQS_QUEUE_URL,
            ReceiptHandle=message["ReceiptHandle"],
        )
    except json.JSONDecodeError:
        log.error("Erro ao decodificar JSON da mensagem ID: %s", message["MessageId"])
    except ClientError as exc:
        log.error("Erro do Boto3 ao processar %s: %s", message["MessageId"], exc)
    except Exception as exc:
        log.error("Erro inesperado ao processar %s: %s", message["MessageId"], exc)


def sqs_worker_loop():
    """Poll SQS and process messages forever."""
    log.info("Iniciando o worker SQS...")
    while True:
        try:
            response = sqs_client.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
            )

            messages = response.get("Messages", [])
            if not messages:
                continue

            log.info("Recebidas %s mensagens.", len(messages))
            for message in messages:
                process_message(message)
        except ClientError as exc:
            log.error("Erro do Boto3 no loop principal do SQS: %s", exc)
            time.sleep(10)
        except Exception as exc:
            log.error("Erro inesperado no loop principal do SQS: %s", exc)
            time.sleep(10)


app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "sqs_worker_enabled": SQS_WORKER_ENABLED,
            "dynamodb_table": DYNAMODB_TABLE_NAME,
        }
    )


def start_worker():
    if not SQS_WORKER_ENABLED:
        log.info("Worker SQS desabilitado. Modo local/health check ativo.")
        return

    worker_thread = threading.Thread(target=sqs_worker_loop, daemon=True)
    worker_thread.start()


threading.Thread(target=ensure_dynamodb_table, daemon=True).start()
start_worker()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8005))
    app.run(host="0.0.0.0", port=port, debug=False)
