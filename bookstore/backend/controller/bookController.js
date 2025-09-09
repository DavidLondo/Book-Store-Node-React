

import { fromEnv } from "@aws-sdk/credential-providers";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, ScanCommand, GetCommand } from "@aws-sdk/lib-dynamodb";

import dotenv from "dotenv";
 
dotenv.config()

const getBooks = async (req, res) => {
  
  if (process.env.NODE_ENV == 'production'){
    var client = new DynamoDBClient({ 
      region: process.env.AWS_REGION, 
    });
  }else{
    var client = new DynamoDBClient({ 
      region: process.env.AWS_REGION, 
      credentials: fromEnv() 
    });
  }

  const docClient = DynamoDBDocumentClient.from(client);
  const command = new ScanCommand({
    TableName: "tb_books",
  });

  const response = await docClient.send(command);

  const books = [];
  for (var i in response.Items) {
    books.push(response.Items[i]);
  }

  res.contentType = 'application/json';
  console.log(books);
  res.json(books);

  return res;

};

const getBooksById = async (req, res) => {

  if (process.env.NODE_ENV == 'production'){
    var client = new DynamoDBClient({ 
      region: process.env.AWS_REGION, 
    });
  }else{
    var client = new DynamoDBClient({ 
      region: process.env.AWS_REGION, 
      credentials: fromEnv() 
    });
  }

  const docClient = DynamoDBDocumentClient.from(client);

  const command = new GetCommand({
    TableName: "tb_books",
    Key: {
      id: req.params.id,
    },
  });

  const response = await docClient.send(command);
  console.log(response.Item);
  res.json(response.Item)
  return res;
};

export { getBooksById, getBooks }