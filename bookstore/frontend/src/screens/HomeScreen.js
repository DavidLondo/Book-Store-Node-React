import React, { useEffect, useState } from 'react';
import { Row, Col } from 'react-bootstrap';
import api from '../api';
import Book from '../components/Book';

const HomeScreen = () => {
  const [books, setBooks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
  const { data } = await api.get('/books');
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
      <section className="hero mb-4">
        <h1 className="mb-2">Descubre tu próxima lectura</h1>
        <p>Explora nuestra selección curada de libros con ediciones imperdibles.</p>
      </section>
      <h2 className="mb-3">Libros</h2>
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