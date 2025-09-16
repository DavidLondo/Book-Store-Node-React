import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Row, Col, Image, ListGroup, Card, Button } from 'react-bootstrap';
import axios from 'axios';

const BookScreen = () => {
  const { id } = useParams();
  const [book, setBook] = useState(null);

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await axios.get(`/api/books/${id}`);
        setBook(data);
      } catch (e) {
        console.error(e);
      }
    };
    load();
  }, [id]);

  if (!book) return <div>Cargando...</div>;

  return (
    <>
      <Link className="btn btn-light my-3" to="/">Volver</Link>
      <Row>
        <Col md={6}>
          <Image src={book.image} alt={book.name} fluid />
        </Col>
        <Col md={3}>
          <ListGroup variant="flush">
            <ListGroup.Item><h3>{book.name}</h3></ListGroup.Item>
            <ListGroup.Item>Autor: {book.author}</ListGroup.Item>
            <ListGroup.Item>Precio: ${book.price}</ListGroup.Item>
            <ListGroup.Item>Descripción: {book.description}</ListGroup.Item>
          </ListGroup>
        </Col>
        <Col md={3}>
          <Card>
            <ListGroup variant="flush">
              <ListGroup.Item>
                <Row>
                  <Col>Stock</Col>
                  <Col><strong>{book.countInStock}</strong></Col>
                </Row>
              </ListGroup.Item>
              <ListGroup.Item>
                <Button className="btn-block" type="button" disabled={book.countInStock === 0}>
                  Agregar al carrito
                </Button>
              </ListGroup.Item>
            </ListGroup>
          </Card>
        </Col>
      </Row>
    </>
  );
};

export default BookScreen;