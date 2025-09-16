import React from 'react';
import { Card } from 'react-bootstrap';
import { Link } from 'react-router-dom';

const Book = ({ book }) => {
  return (
    <Card className="my-3 p-3 rounded">
      <Link to={`/book/${book.id}`}>
        <Card.Img src={book.image} variant="top" alt={book.name} />
      </Link>
      <Card.Body>
        <Link to={`/book/${book.id}`} style={{ textDecoration: 'none' }}>
          <Card.Title as="div"><strong>{book.name}</strong></Card.Title>
        </Link>
        <Card.Text as="div">{book.author}</Card.Text>
        <div className="d-flex align-items-center justify-content-between mt-2">
          <span className="price">${book.price}</span>
        </div>
      </Card.Body>
    </Card>
  );
};

export default Book;