import React, { useEffect, useState } from 'react';
import { Row, Col } from 'react-bootstrap';
import axios from 'axios';
import Book from '../components/Book';

const HomeScreen = () => {
  const [books, setBooks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const { data } = await axios.get('/api/books');
        setBooks(data);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  if (loading) return <div>Cargando...</div>;

  return (
    <>
      <h1>Libros</h1>
      <Row>
        {books.map((b) => (
          <Col key={b.id} sm={12} md={6} lg={4} xl={3}>
            <Book book={b} />
          </Col>
        ))}
      </Row>
    </>
  );
};

export default HomeScreen;