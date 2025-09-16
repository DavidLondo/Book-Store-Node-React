import dotenv from "dotenv";
import { DynamoDBClient, CreateTableCommand, DescribeTableCommand } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, PutCommand } from "@aws-sdk/lib-dynamodb";

dotenv.config();

const region = process.env.AWS_REGION || process.env.REGION || "us-east-1";
const endpoint = process.env.DDB_ENDPOINT; // Only set for local dev
const TableName = process.env.TABLE_NAME || "tb_books";

// Use local endpoint with dummy creds only when explicitly provided; otherwise
// rely on instance role/default provider chain for AWS.
const clientConfig = endpoint
  ? { region, endpoint, credentials: { accessKeyId: "fake", secretAccessKey: "fake" } }
  : { region };

const client = new DynamoDBClient(clientConfig);
const docClient = DynamoDBDocumentClient.from(client);

async function ensureTable() {
  try {
    await client.send(new DescribeTableCommand({ TableName }));
    console.log(`Tabla ${TableName} ya existe`);
  } catch (err) {
    if (err.name === "ResourceNotFoundException") {
      console.log(`Creando tabla ${TableName}...`);
      await client.send(
        new CreateTableCommand({
          TableName,
          AttributeDefinitions: [{ AttributeName: "id", AttributeType: "S" }],
          KeySchema: [{ AttributeName: "id", KeyType: "HASH" }],
          BillingMode: "PAY_PER_REQUEST",
        })
      );
      console.log("Esperando a que la tabla esté activa...");
      // Pequeña espera simple
      await new Promise((r) => setTimeout(r, 3000));
    } else {
      throw err;
    }
  }
}

async function seed() {
  const items = [
    {
      id: "1",
      name: "Liderazgo",
      author: "Howard K.",
      description: "Guía práctica de liderazgo.",
      image: "/images/img-hk-liderazgo.jpeg",
      countInStock: 12,
      price: 19.99,
    },
    {
      id: "2",
      name: "Inteligencia Genial",
      author: "Luis D.",
      description: "Exploración de la inteligencia humana.",
      image: "/images/img-ld-inteligenciagenial.jpeg",
      countInStock: 5,
      price: 14.5,
    },
    {
      id: "3",
      name: "La Biografía",
      author: "Luis D.",
      description: "Relato biográfico inspirador.",
      image: "/images/img-ld-labiografia.jpeg",
      countInStock: 7,
      price: 22.0,
    },
    {
      id: "4",
      name: "Meditaciones",
      author: "Marco A.",
      description: "Reflexiones filosóficas clásicas.",
      image: "/images/img-ma-meditaciones.jpeg",
      countInStock: 20,
      price: 11.95,
    },
  ];

  for (const item of items) {
    await docClient.send(new PutCommand({ TableName, Item: item }));
  }
  console.log(`Seed completado: ${items.length} items en ${TableName}`);
}

// In AWS (no endpoint), we assume the table is provisioned by infra and skip creation.
const run = endpoint ? ensureTable().then(seed) : seed();

run
  .catch((e) => {
    console.error(e);
    process.exit(1);
  });