import unittest
import os
from app import create_app, db
from app.models import User


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        print("Current working directory:", os.getcwd())
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'WTF_CSRF_ENABLED': False,
            'SERVER_NAME': 'localhost.localdomain',
            'SECRET_KEY': 'test_secret_key'
        })

        print("App instance created")
        print("App template folder:", self.app.template_folder)
        self.app_context = self.app.app_context()
        self.app_context.push()
        print("App context pushed")
        self.client = self.app.test_client()
        db.create_all()
        print("Database tables created")

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_register_and_login(self):
        # Test registration
        response = self.client.post('/register', data={
            'username': 'testuser',
            'email': 'test@example.com',
            'password': 'password'
        }, follow_redirects=True)
        print(f"Registration Response: {response.status_code}")
        print(f"Response Data: {response.data}")
        self.assertEqual(response.status_code, 200)

        # Verify user in database
        user = User.query.filter_by(email='test@example.com').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.username, 'testuser')

        # Test login
        response = self.client.post('/login', data={
            'email': 'test@example.com',
            'password': 'password'
        }, follow_redirects=True)
        print(f"Login Response: {response.status_code}")
        print(f"Response Data: {response.data}")
        self.assertEqual(response.status_code, 200)

        # Check login was successful by accessing a protected route
        response = self.client.get('/stock/list')
        print(f"Protected Route Response: {response.status_code}")
        print(f"Response Data: {response.data}")
        self.assertEqual(response.status_code, 200)


if __name__ == '__main__':
    unittest.main()
