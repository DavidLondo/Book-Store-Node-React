import React, { useState, useEffect } from 'react';
import axios from 'axios';

import { Link, useParams } from 'react-router-dom';
import { Row, Col, Image, ListGroup } from 'react-bootstrap';
import { Button } from 'react-bootstrap';


const BookScreen = ({ match }) => {

    const [book, setBook] = useState({})
    const { id } = useParams();

    useEffect(() => {
        const fetchBook = async () => {
            const { data } = await axios.get(`/api/books/${id}`)
            setBook(data)
        }
        fetchBook()
    }, [id])


    return (
        <>
            <Link to='/' style={{ textDecoration: 'none' }}>
                <Button variant='light' className='my-3' aria-label="Regresar a la página principal">
                    Regresar al Catálogo
                </Button>
            </Link>
            <Row>
                <Col md={4}>
                    <Image src={book.image} alt={book.name} fluid />
                </Col>

                <Col md={4}>
                    <ListGroup variant='flush'>
                        <ListGroup.Item><h3>{book.name}</h3></ListGroup.Item>
                        <ListGroup.Item>Autor: {book.author}</ListGroup.Item>
                        <ListGroup.Item variant='flush'>Descripción: {book.description}</ListGroup.Item>
                    </ListGroup>
                </Col>
                <Col md={3}>
                    <ListGroup variant='flush'>
                        <ListGroup.Item>
                            Estado: {book.countInStock > 0 ? 'Disponible' : 'No Disponible'} ({book.countInStock}) uds
                        </ListGroup.Item>
                        <ListGroup.Item><strong>Precio:</strong> {book.price}</ListGroup.Item>
                    </ListGroup>
                </Col>

            </Row>
        </>
    )
}

export default BookScreen

