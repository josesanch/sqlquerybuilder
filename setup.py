# encoding: utf-8
from distutils.core import setup
from setuptools import find_packages
import sqlquerybuilder

setup(
    name='sqlquerybuilder',
    version=sqlquerybuilder.VERSION,
    author='José Sánchez Moreno',
    author_email='jose@o2w.es',
    packages=find_packages(),
    test_suite="tests",
    license='MIT',
    description=u'SQL Query Builder inspired on django ORM Syntax',
    long_description=open('README.rst').read(),
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
        'Programming Language :: SQL',
    ],

)
