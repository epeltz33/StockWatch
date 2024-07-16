import unittest
from app import create_app, db
from app.models import User
from flask import url_for

class AuthTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_register_and_login(self):
        # Test registration
        response = self.client.post(url_for('auth.register'), data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password'
        })
        self.assertEqual(response.status_code, 302)  # Redirect to login

        # Verify user in database
        with self.app.app_context():
            user = User.query.filter_by(email='test@example.com').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.username, 'testuser')

        # Test login
        response = self.client.post(url_for('auth.login'), data={
            'email': 'test@example.com',
            'password': 'password'
        })
        self.assertEqual(response.status_code, 302)  # Redirect after login

        # Check login was successful by accessing a protected route
        response = self.client.get(url_for('stock.list_stocks'))
        self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()