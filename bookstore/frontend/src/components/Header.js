import React from 'react';
import { Navbar, Nav, Container } from 'react-bootstrap';
import { LinkContainer } from 'react-router-bootstrap';

const Header = () => {
  return (
    <header>
      <Navbar bg="light" variant="light" expand="lg" collapseOnSelect className="shadow-sm">
        <Container>
          <LinkContainer to="/">
            <Navbar.Brand>
              <span style={{ fontWeight: 800 }}>Book</span> <span style={{ color: '#00d4ff' }}>Store</span>
            </Navbar.Brand>
          </LinkContainer>
          <Navbar.Toggle aria-controls="basic-navbar-nav" />
          <Navbar.Collapse id="basic-navbar-nav">
            <Nav className="ms-auto">
              <LinkContainer to="/">
                <Nav.Link>Inicio</Nav.Link>
              </LinkContainer>
              <LinkContainer to="/about">
                <Nav.Link>Acerca</Nav.Link>
              </LinkContainer>
            </Nav>
          </Navbar.Collapse>
        </Container>
      </Navbar>
    </header>
  );
};

export default Header;