import dotenv from "dotenv";
import {
  DynamoDBClient,
  CreateTableCommand,
  DescribeTableCommand,
  ResourceNotFoundException,
} from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, PutCommand } from "@aws-sdk/lib-dynamodb";

dotenv.config();

const region = process.env.AWS_REGION || process.env.REGION || "us-east-1";
const endpoint = process.env.DDB_ENDPOINT; // solo local
const TableName = process.env.TABLE_NAME || "tb_books";

const client = new DynamoDBClient(
  endpoint
    ? { region, endpoint, credentials: { accessKeyId: "fake", secretAccessKey: "fake" } }
    : { region } // en AWS usa el role de la instancia
);
const docClient = DynamoDBDocumentClient.from(client);

async function ensureTableExists() {
  // Solo crear la tabla en entorno local (cuando usamos endpoint)
  if (!endpoint) return;

  const describe = async () => {
    try {
      const res = await client.send(new DescribeTableCommand({ TableName }));
      return res.Table?.TableStatus;
    } catch (e) {
      if (e instanceof ResourceNotFoundException) return "NOT_FOUND";
      throw e;
    }
  };

  // Esperar hasta que DynamoDB Local esté listo (reintentos)
  for (let i = 0; i < 10; i++) {
    try {
      const status = await describe();
      if (status && status !== "NOT_FOUND") return; // Ya existe
      break;
    } catch (e) {
      await new Promise((r) => setTimeout(r, 1000 * (i + 1)));
    }
  }

  const status = await describe();
  if (status === "NOT_FOUND") {
    console.log(`Creando tabla ${TableName} en DynamoDB Local...`);
    await client.send(
      new CreateTableCommand({
        TableName,
        BillingMode: "PAY_PER_REQUEST",
        AttributeDefinitions: [{ AttributeName: "id", AttributeType: "S" }],
        KeySchema: [{ AttributeName: "id", KeyType: "HASH" }],
      })
    );
  }

  // Esperar a que esté ACTIVE
  for (let i = 0; i < 20; i++) {
    const s = await describe();
    if (s === "ACTIVE") return;
    await new Promise((r) => setTimeout(r, 500));
  }
}

async function seed() {
  await ensureTableExists();
  const items = [
    { id: "1", name: "Liderazgo", author: "Howard K.", description: "Guía práctica de liderazgo.", image: "/images/img-hk-liderazgo.jpeg", countInStock: 12, price: 19.99 },
    { id: "2", name: "Inteligencia Genial", author: "Luis D.", description: "Exploración de la inteligencia humana.", image: "/images/img-ld-inteligenciagenial.jpeg", countInStock: 5, price: 14.5 },
    { id: "3", name: "La Biografía", author: "Luis D.", description: "Relato biográfico inspirador.", image: "/images/img-ld-labiografia.jpeg", countInStock: 7, price: 22.0 },
    { id: "4", name: "Meditaciones", author: "Marco A.", description: "Reflexiones filosóficas clásicas.", image: "/images/img-ma-meditaciones.jpeg", countInStock: 20, price: 11.95 },
  ];
  for (const item of items) {
    await docClient.send(new PutCommand({ TableName, Item: item }));
  }
  console.log(`Seed completado: ${items.length} items en ${TableName}`);
}

seed()
  .then(() => process.exit(0))
  .catch((e) => {
    console.error(e);
    process.exit(0); // no bloquear arranque si falla en AWS
  });