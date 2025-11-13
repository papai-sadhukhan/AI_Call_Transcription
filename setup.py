import setuptools

# Required for Dataflow to install custom modules on workers
setuptools.setup(
    name='skydata-genai-tf',
    version='1.0.0',
    packages=setuptools.find_packages(),
    install_requires=[
        'apache-beam[gcp]==2.61.0',
        'presidio-analyzer==2.2.359',
        'presidio-anonymizer==2.2.359',
        'spacy==3.7.2',
        'pandas',
        'PyYAML',
    ],
)
