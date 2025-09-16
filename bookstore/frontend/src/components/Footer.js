import React from 'react';
import { Container, Row, Col } from 'react-bootstrap';

const Footer = () => (
  <footer>
    <Container>
      <Row>
        <Col className="text-center py-3">Book Store © {new Date().getFullYear()}</Col>
      </Row>
    </Container>
  </footer>
);

export default Footer;