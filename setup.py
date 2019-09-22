"""Setup script"""

from setuptools import find_packages, setup

extras_require = { # pylint: disable=invalid-name
    'lint': [
        'pylint>=2.3.0,<3'
    ],
    'dev': [
        'rope>=0.14.0,<0.15'
    ]
}

extras_require['dev'] = (
    extras_require['lint'] +
    extras_require['dev']
)

setup(
    name='gasstation-express-oracle',
    version='0.1.0',
    license='MIT',
    description='Ethereum Gas Price Oracle',
    long_description_markdown_filename='README.md',
    author='Marcus R. Brown',
    author_email='contact@marcusrbrown.com',
    url='https://github.com/igetgames/gasstation-express-oracle',
    packages=find_packages(),
    scripts=['gasstation-express-oracle'],
    include_package_data=True,
    python_requires='>=3.6,<4',
    install_requires=[
        'numpy==1.13.3',
        'pandas==0.21.0',
        'web3==3.16.4',
    ],
    setup_requires=['setuptools-markdown'],
    extras_require=extras_require,
    zip_safe=True,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ]
)
