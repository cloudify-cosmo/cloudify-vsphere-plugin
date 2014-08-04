__author__ = 'Oleksandr_Raskosov'


from setuptools import setup


setup(
    zip_safe=True,
    name='cloudify-vsphere-plugin',
    version='1.0',
    author='Oleksandr_Raskosov',
    author_email='Oleksandr_Raskosov@epam.com',
    packages=[
        'vsphere_plugin_common',
        'server_plugin',
        'network_plugin',
        'storage_plugin'
    ],
    license='LICENSE',
    description='Cloudify plugin for vSphere infrastructure.',
    install_requires=[
        "cloudify-plugins-common>=3.0",
        "pyvmomi",
    ]
)
