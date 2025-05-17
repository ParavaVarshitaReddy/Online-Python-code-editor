import os
import tempfile
import docker
from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
import time # For debugging timestamps
import traceback # For detailed exception printing
import socket # For socket.SHUT_WR

app = Flask(__name__)
CORS(app)

try:
    client = docker.from_env()
    print("Docker client initialized. Available images:", [img.tags for img in client.images.list() if img.tags])
except docker.errors.DockerException as e:
    print(f"Could not connect to Docker daemon. Is Docker running? Error: {e}")
    client = None

@app.route('/api/execute', methods=['POST'])
def execute_code():
    if not client:
        print(f"[{time.time()}] ERROR: Docker client not available. Cannot execute code.")
        return jsonify({
            "output": "",
            "error": "Docker service is not available or not connected. Cannot execute code."
        }), 503 # Service Unavailable

    # This line was causing the IndentationError because it was not indented under an 'else' or after the 'if' block was properly handled.
    # Now that the 'if not client:' block has a 'return', the rest of the code implicitly becomes the 'else' part.
    data = request.get_json()
    code = data.get('code', '')
    user_input = data.get('input', '')
    input_to_send = user_input + '\n'

    # Create a temporary directory to store user code and handle I/O
    with tempfile.TemporaryDirectory() as temp_dir:
        script_filename = f"user_script_{uuid.uuid4().hex}.py"
        script_path_host = os.path.join(temp_dir, script_filename)

        with open(script_path_host, 'w') as f:
            f.write(code)

        command_to_run = ["python", script_filename]
        container_output = ""
        container_error = ""
        container_obj = None # Initialize to None

        try:
            print(f"[{time.time()}] DEBUG: Received code:\n{code[:300]}...") # Log truncated code
            print(f"[{time.time()}] DEBUG: Received input field value: '{user_input[:100]}'")
            print(f"[{time.time()}] DEBUG: Input to send to container (with newline): '{input_to_send[:100]}'")

            print(f"[{time.time()}] DEBUG: About to create container.")
            container_obj = client.containers.create(
                image='python-runner',
                command=command_to_run,
                volumes={temp_dir: {'bind': '/usr/src/app', 'mode': 'rw'}},
                working_dir='/usr/src/app',
                stdin_open=True,
                tty=False,
                # network_mode='none' # Optional for more security
            )
            print(f"[{time.time()}] DEBUG: Container created: {container_obj.id}")

            print(f"[{time.time()}] DEBUG: About to start container.")
            container_obj.start()
            print(f"[{time.time()}] DEBUG: Container started.")
            
            print(f"[{time.time()}] DEBUG: About to attach socket for stdin/stdout/stderr.")
            raw_socket = container_obj.attach_socket(params={'stdin': 1, 'stdout': 1, 'stderr': 1, 'stream': 1})
            print(f"[{time.time()}] DEBUG: Socket attached. Type: {type(raw_socket)}") # Log socket type

            if hasattr(raw_socket, '_sock') and hasattr(raw_socket._sock, 'sendall'): # Check for legacy _sock access if direct sendall fails
                # This is a common pattern for older docker-py or specific socket wrappers
                actual_socket_to_write = raw_socket._sock
                print(f"[{time.time()}] DEBUG: Using raw_socket._sock.sendall() for input: '{input_to_send[:100]}'")
                actual_socket_to_write.sendall(input_to_send.encode('utf-8'))
                print(f"[{time.time()}] DEBUG: Input sent via _sock.sendall.")
                if hasattr(actual_socket_to_write, 'shutdown'):
                    actual_socket_to_write.shutdown(socket.SHUT_WR)
                    print(f"[{time.time()}] DEBUG: _sock.shutdown(SHUT_WR) called.")
                else:
                    # If no shutdown, closing the main raw_socket later should handle it.
                    print(f"[{time.time()}] DEBUG: _sock has no shutdown method. Relying on raw_socket.close() later.")

            elif hasattr(raw_socket, 'sendall'): # Check if raw_socket itself is directly writable
                print(f"[{time.time()}] DEBUG: Using raw_socket.sendall() directly for input: '{input_to_send[:100]}'")
                raw_socket.sendall(input_to_send.encode('utf-8'))
                print(f"[{time.time()}] DEBUG: Input sent via raw_socket.sendall.")
                # For Npipe or some stream objects, simply closing the stream is how EOF is signaled.
                # The shutdown method might not be available or might error.
                # We will close raw_socket in the finally block of its usage if needed,
                # or after reading output if we were streaming.
                # For now, let's assume input() in Python will read until the stream is closed.
                # Python's `input()` reads until newline, then the next `input()` waits.
                # It needs the *entire input stream* to be closed for it to know there are no more `input()` lines.
                # This is often done by closing the write-half of the socket or the whole socket.
                # For `NpipeSocket` this can be tricky. Let's try closing it after sending.
                if hasattr(raw_socket, 'shutdown') and callable(getattr(raw_socket, 'shutdown')):
                    try:
                        raw_socket.shutdown(socket.SHUT_WR)
                        print(f"[{time.time()}] DEBUG: raw_socket.shutdown(SHUT_WR) called.")
                    except Exception as e_shut:
                        print(f"[{time.time()}] DEBUG: raw_socket.shutdown(SHUT_WR) failed: {e_shut}. Will try close().")
                        raw_socket.close() # Fallback to close if shutdown fails
                        print(f"[{time.time()}] DEBUG: raw_socket.close() called after shutdown attempt.")
                else:
                    raw_socket.close() # If no shutdown, try close() directly
                    print(f"[{time.time()}] DEBUG: raw_socket.close() called (no shutdown attr or not callable).")


            else:
                print(f"[{time.time()}] DEBUG: raw_socket (type: {type(raw_socket)}) does not have sendall or _sock.sendall. Cannot send input.")
                # This is an issue, as we can't send input to the container.
                # The script will likely hang if it calls input().
                # We should probably error out here or handle it.
                # For now, we'll let it proceed and see if it hangs at wait().

            print(f"[{time.time()}] DEBUG: About to wait for container.")
            # Timeout should be generous enough for simple scripts but prevent infinite hangs.
            result = container_obj.wait(timeout=20) # Timeout after 20 seconds
            exit_code = result.get('StatusCode', -1)
            print(f"[{time.time()}] DEBUG: Container wait finished. Exit code: {exit_code}")

            # Get logs (stdout and stderr)
            stdout_logs_bytes = container_obj.logs(stdout=True, stderr=False, stream=False)
            stderr_logs_bytes = container_obj.logs(stdout=False, stderr=True, stream=False)

            if stdout_logs_bytes:
                container_output = stdout_logs_bytes.decode('utf-8', errors='replace')
            if stderr_logs_bytes:
                container_error = stderr_logs_bytes.decode('utf-8', errors='replace')
            
            print(f"[{time.time()}] DEBUG: Container stdout:\n{container_output}")
            print(f"[{time.time()}] DEBUG: Container stderr:\n{container_error}")

            if exit_code != 0 and not container_error: # If script errored but didn't print to stderr
                container_error = f"Script exited with error code {exit_code}."
                if container_output: # Prepend stdout if any, as it might be relevant
                     container_error = f"{container_output}\n{container_error}"
                     container_output = "" # Clear stdout as it's now part of the error message

        except docker.errors.ContainerError as e:
            print(f"[{time.time()}] ERROR: Docker ContainerError: {e}")
            traceback.print_exc()
            # The error object 'e' itself often contains the container's stderr
            container_error = str(e.stderr.decode('utf-8', errors='replace') if e.stderr else e)
            try:
                if e.container: # Check if container object exists on exception
                    stdout_from_error = e.container.logs(stdout=True, stderr=False).decode('utf-8', errors='replace')
                    if stdout_from_error:
                        container_output = stdout_from_error
                        print(f"[{time.time()}] DEBUG: Stdout from ContainerError context:\n{container_output}")
            except Exception as log_err_ctx:
                print(f"[{time.time()}] DEBUG: Could not retrieve stdout from ContainerError context: {log_err_ctx}")

        except docker.errors.APIError as e_api:
            print(f"[{time.time()}] ERROR: Docker APIError: {e_api}")
            traceback.print_exc()
            container_error = f"Docker API error: {str(e_api)}"
        except Exception as e_general:
            print(f"[{time.time()}] ERROR: An unexpected exception occurred in backend: {type(e_general).__name__} - {e_general}")
            traceback.print_exc()
            container_error = f"An unexpected server error occurred: {str(e_general)}"
        finally:
            # Close the raw socket if it was opened and not closed yet
            if 'raw_socket' in locals() and raw_socket:
                try:
                    if not raw_socket.closed: # Check if it has a 'closed' attribute and if it's not closed
                        raw_socket.close()
                        print(f"[{time.time()}] DEBUG: raw_socket closed in finally block.")
                except Exception as e_close_raw_socket:
                    print(f"[{time.time()}] DEBUG: Error closing raw_socket in finally: {e_close_raw_socket}")

            if container_obj:
                print(f"[{time.time()}] DEBUG: About to remove container {container_obj.id} in finally block.")
                try:
                    container_obj.remove(force=True)
                    print(f"[{time.time()}] DEBUG: Container removed in finally block.")
                except docker.errors.NotFound:
                    print(f"[{time.time()}] DEBUG: Container {container_obj.id} already removed or not found (in finally).")
                except Exception as e_remove:
                    print(f"[{time.time()}] DEBUG: Error removing container {container_obj.id} in finally: {e_remove}")
    
    response_data = {
        "output": container_output,
        "error": container_error
    }
    return jsonify(response_data)

@app.route('/')
def index():
    return "Hello from the Python Backend! The server is running. Docker client should be initialized if Docker is running."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)