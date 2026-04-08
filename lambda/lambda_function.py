"""
Lambda console default entry file: set Handler to lambda_function.lambda_handler
and include both this file and discovery_handler.py in the deployment package.
"""
from discovery_handler import lambda_handler  # noqa: F401

__all__ = ["lambda_handler"]
