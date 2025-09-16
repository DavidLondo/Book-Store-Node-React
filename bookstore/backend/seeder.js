import dotenv from "dotenv";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
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

async function seed() {
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

seed().catch((e) => {
  console.error(e);
  process.exit(0); // no bloquear arranque si falla en AWS
});