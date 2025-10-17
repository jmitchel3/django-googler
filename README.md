# Django Hookflow
Trigger GitHub Actions workflows from Django.

## Installation

```bash
pip install django-hookflow
```

Depends on:

- [Python 3.10+](https://www.python.org/)
- [Django 5+](https://docs.djangoproject.com/)

## Usage

```python
from django_hookflow import trigger_github_workflow


@trigger_github_workflow(repo="user/repo", workflow_file="workflow.yml")
def math_add_task(a, b, save_to_file=False):
    logger.info(f"Adding {a} and {b}")
    if save_to_file:
        with open("math-add-result.txt", "w") as f:
            f.write(f"{a} + {b} = {a + b}")
    return a + b
```

```python
from django_hookflow import dispatch_workflow

dispatch_workflow(repo="user/repo", workflow_file="workflow.yml")
```
