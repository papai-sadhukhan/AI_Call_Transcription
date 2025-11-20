from setuptools import setup, find_packages

setup(
    name='skydata-genai-tf',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[
        'apache-beam[gcp]==2.61.0',
        'presidio-analyzer==2.2.359',
        'presidio-anonymizer==2.2.359',
        'spacy==3.7.2',
    ],
)
