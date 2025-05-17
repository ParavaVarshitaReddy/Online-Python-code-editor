# Use an official lightweight Python image as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /usr/src/app

# We don't need to copy any application code into this image permanently,
# as the user's code will be mounted or copied in at runtime.
# This image is just the execution environment.

# When the container starts, Python will be the default command.
# We will provide the script to run dynamically.
CMD ["python"]