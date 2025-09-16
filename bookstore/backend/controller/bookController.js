import { ScanCommand, GetCommand } from "@aws-sdk/lib-dynamodb";
import { docClient, TABLE_NAME } from "../config/dynamo.js";

const getBooks = async (req, res) => {
  try {
    const command = new ScanCommand({
      TableName: TABLE_NAME,
    });

    const response = await docClient.send(command);
    const books = response.Items || [];

    res.json(books);
  } catch (err) {
    console.error("Error en getBooks:", err);
    res.status(500).json({ message: "Error obteniendo libros" });
  }
};

const getBooksById = async (req, res) => {
  try {
    const command = new GetCommand({
      TableName: TABLE_NAME,
      Key: { id: req.params.id }, // asegúrate que la PK sea "id"
    });

    const response = await docClient.send(command);

    if (!response.Item) {
      return res.status(404).json({ message: "Libro no encontrado" });
    }

    res.json(response.Item);
  } catch (err) {
    console.error("Error en getBooksById:", err);
    res.status(500).json({ message: "Error obteniendo el libro" });
  }
};

export { getBooks, getBooksById };
