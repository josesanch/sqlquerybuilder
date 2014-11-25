# encoding: utf-8
from distutils.core import setup
from setuptools import find_packages

setup(
    name='sqlquerybuilder',
    version='0.0.2',
    author='José Sánchez Moreno',
    author_email='jose@o2w.es',
    packages=find_packages(),
    license='LICENSE.txt',
    description=u'SQL Query Builder inspired on django ORM Syntax',
    long_description=open('README.txt').read(),
    url='https://github.com/josesanch/sqlquerybuilder',
    platforms="All platforms",

    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Python Software Foundation License',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX',
        'Programming Language :: Python',
    ],

)
