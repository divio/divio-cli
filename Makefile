# can also be used as `make ARGS=--check black` for example
black:
	find divio_cli -name '*.py' | xargs black --line-length=79 --safe $(ARGS)

isort:
	isort -rc divio_cli

autoflake:
	find divio_cli -name '*.py' | xargs autoflake --in-place --remove-unused-variables

# isort must come first as black reformats the imports again
lint: autoflake isort black