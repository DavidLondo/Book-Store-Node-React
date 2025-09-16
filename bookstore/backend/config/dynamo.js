import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";

const client = new DynamoDBClient({
  region: "us-east-1", // LabRole ya da permisos
});

const docClient = DynamoDBDocumentClient.from(client);

const TABLE_NAME = "tb_books";

export { docClient, TABLE_NAME };
