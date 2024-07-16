import unittest
from app import create_app, db
from app.models import User
from flask import url_for

class AuthTestCase(unittest.TestCase):
  def setUp(self):
    self.app = create_app()
    self.app.config['TESTING'] = True
    self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with self.app.app_context():
      db.create_all()


