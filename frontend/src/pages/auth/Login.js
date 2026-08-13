import React from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faAngleLeft, faUnlockAlt, faUser } from "@fortawesome/free-solid-svg-icons";
import { Col, Row, Form, Card, Button, FormCheck, Container, InputGroup } from "@themesberg/react-bootstrap";
import { Link } from "react-router-dom";

import { Routes } from "../../routes";
import BgImage from "../../assets/img/illustrations/signin.svg";

/** Login shell — API wiring arrives in later Prompt 7 steps. */
export default () => (
  <main>
    <section className="d-flex align-items-center my-5 mt-lg-6 mb-lg-5">
      <Container>
        <p className="text-center">
          <Card.Link as={Link} to={Routes.Dashboard.path} className="text-gray-700">
            <FontAwesomeIcon icon={faAngleLeft} className="me-2" /> Back to dashboard
          </Card.Link>
        </p>
        <Row
          className="justify-content-center form-bg-image"
          style={{ backgroundImage: `url(${BgImage})` }}
        >
          <Col xs={12} className="d-flex align-items-center justify-content-center">
            <div className="bg-white shadow-soft border rounded border-light p-4 p-lg-5 w-100 fmxw-500">
              <div className="text-center text-md-center mb-4 mt-md-0">
                <h3 className="mb-0">Sign in to DFAT</h3>
                <p className="text-gray">Digital Forensics Automation Tool</p>
              </div>
              <Form className="mt-4">
                <Form.Group id="username" className="mb-4">
                  <Form.Label>Username</Form.Label>
                  <InputGroup>
                    <InputGroup.Text>
                      <FontAwesomeIcon icon={faUser} />
                    </InputGroup.Text>
                    <Form.Control
                      autoFocus
                      required
                      type="text"
                      placeholder="investigator"
                    />
                  </InputGroup>
                </Form.Group>
                <Form.Group id="password" className="mb-4">
                  <Form.Label>Password</Form.Label>
                  <InputGroup>
                    <InputGroup.Text>
                      <FontAwesomeIcon icon={faUnlockAlt} />
                    </InputGroup.Text>
                    <Form.Control required type="password" placeholder="Password" />
                  </InputGroup>
                </Form.Group>
                <div className="d-flex justify-content-between align-items-center mb-4">
                  <Form.Check type="checkbox">
                    <FormCheck.Input id="rememberMe" className="me-2" />
                    <FormCheck.Label htmlFor="rememberMe" className="mb-0">
                      Remember me
                    </FormCheck.Label>
                  </Form.Check>
                </div>
                <Button variant="primary" type="submit" className="w-100">
                  Sign in
                </Button>
              </Form>
              <div className="d-flex justify-content-center align-items-center mt-4">
                <span className="fw-normal">
                  Need an account?{" "}
                  <Card.Link as={Link} to={Routes.Register.path} className="fw-bold">
                    Register
                  </Card.Link>
                </span>
              </div>
            </div>
          </Col>
        </Row>
      </Container>
    </section>
  </main>
);
