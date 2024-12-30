from setuptools import setup, find_packages

setup(
    name="stockwatch",
    version="0.1",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'flask',
        'flask-sqlalchemy',
        'flask-migrate',
        'flask-login',
        'flask-caching',
        'polygon-api-client',
    ],
    extras_require={
        'test': [
            'pytest',
            'pytest-mock',
            'pytest-cov',
        ],
    },
)