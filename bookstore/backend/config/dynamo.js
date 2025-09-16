import dotenv from 'dotenv';
dotenv.config();

import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { NodeHttpHandler } from "@smithy/node-http-handler";
import { DynamoDBDocumentClient } from "@aws-sdk/lib-dynamodb";

const region = process.env.AWS_REGION || process.env.REGION || "us-east-1";
const endpoint = process.env.DDB_ENDPOINT; // http://localhost:8000

const requestHandler = new NodeHttpHandler({ connectionTimeout: 2000, socketTimeout: 5000 });

const clientConfig = endpoint
  ? {
      region,
      endpoint,
      credentials: {
        accessKeyId: "fake",
        secretAccessKey: "fake",
      },
      requestHandler,
    }
  : { region, requestHandler };

const client = new DynamoDBClient(clientConfig);
export const docClient = DynamoDBDocumentClient.from(client);
export const TABLE_NAME = process.env.TABLE_NAME || "tb_books";