"""
Test web interface startup and functionality.
"""
import subprocess
import time
import requests
import threading
from concurrent.futures import ThreadPoolExecutor


def start_server():
    """Start the web server in a separate process."""
    return subprocess.Popen(
        ["python", "-c", """
from mockworkflow.web.app import app
import uvicorn
uvicorn.run(app, host='0.0.0.0', port=8000, reload=False)
"""],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )


class TestWebInterface:
    """Comprehensive test for web interface functionality."""

    def __init__(self):
        self.server = None
        self.base_url = "http://localhost:8000"

    def setup(self):
        """Set up the test environment."""
        print("Starting web server...")
        self.server = start_server()
        # Wait for server to start
        time.sleep(3)

    def teardown(self):
        """Tear down the test environment."""
        if self.server:
            print("Stopping server...")
            self.server.terminate()
            self.server.wait()
            print("Server stopped.")

    def test_health_check(self):
        """Test health check endpoint."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert "timestamp" in data
            print(f"✓ Health check passed: {response.status_code}")
        except Exception as e:
            print(f"✗ Health check failed: {e}")
            raise

    def test_websocket_endpoint(self):
        """Test WebSocket endpoint availability."""
        try:
            import websocket
            ws = websocket.WebSocket()
            ws.connect("ws://localhost:8000/ws/tasks")
            assert ws.connected is True
            ws.close()
            print("✓ WebSocket endpoint is available")
        except ImportError:
            print("WebSocket library not available, skipping WebSocket test")
        except Exception as e:
            print(f"✗ WebSocket connection failed: {e}")
            raise

    def test_statistics_api(self):
        """Test statistics API endpoints."""
        try:
            # Test task statistics summary
            stats_response = requests.get(f"{self.base_url}/api/tasks/stats/summary", timeout=5)
            assert stats_response.status_code == 200
            stats = stats_response.json()
            expected_fields = [
                "total_tasks", "status_distribution", "daily_counts",
                "success_rate", "top_tables", "avg_rows",
                "avg_completion_time", "total_rows_generated"
            ]
            for field in expected_fields:
                assert field in stats, f"Missing field {field} in stats response"
            print("✓ Statistics API returned expected fields")
        except Exception as e:
            print(f"✗ Statistics API test failed: {e}")
            raise

    def test_sample_files_listing(self):
        """Test listing of sample files."""
        try:
            response = requests.get(f"{self.base_url}/api/samples", timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert "samples" in data
            assert isinstance(data["samples"], list)
            print(f"✓ Found {len(data['samples'])} sample files")
        except Exception as e:
            print(f"✗ Sample files listing failed: {e}")
            raise

    def test_upload_functionality(self):
        """Test file upload functionality."""
        try:
            # Test with a small CSV file
            csv_content = "header1,header2\nvalue1,value2\n"
            files = {'file': ('test_upload.csv', csv_content, 'text/csv')}
            response = requests.post(f"{self.base_url}/api/upload", files=files, timeout=5)
            assert response.status_code == 200
            result = response.json()
            assert "message" in result
            assert "File uploaded successfully" in result["message"]
            assert "filename" in result
            assert result["filename"] == "test_upload.csv"
            print("✓ File upload functionality works")
        except Exception as e:
            print(f"✗ Upload functionality test failed: {e}")
            raise

    def test_batch_task_creation(self):
        """Test batch task creation functionality."""
        try:
            # First ensure there's a sample file
            samples_response = requests.get(f"{self.base_url}/api/samples", timeout=5)
            samples = samples_response.json()["samples"]
            if not samples:
                print("No sample files available for batch task test")
                return

            sample_file = samples[0]["path"]

            # Test batch task creation
            batch_data = {
                "tasks": [
                    {
                        "sample_filename": sample_file,
                        "table_name": "batch_test_1",
                        "rows": 10
                    },
                    {
                        "sample_filename": sample_file,
                        "table_name": "batch_test_2",
                        "rows": 20
                    }
                ],
                "auto_table_name": False
            }
            response = requests.post(
                f"{self.base_url}/api/tasks/batch",
                json=batch_data,
                timeout=5
            )
            assert response.status_code == 201
            result = response.json()
            assert "task_ids" in result
            assert len(result["task_ids"]) == 2
            assert result["created_count"] == 2
            print("✓ Batch task creation works")
        except Exception as e:
            print(f"✗ Batch task creation test failed: {e}")
            raise

    def test_concurrent_requests(self):
        """Test handling of concurrent requests."""
        try:
            # Make multiple concurrent requests to health check
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [
                    executor.submit(
                        requests.get,
                        f"{self.base_url}/health",
                        timeout=5
                    ) for _ in range(5)
                ]
                results = [f.result() for f in futures]

            # Verify all requests succeeded
            for i, result in enumerate(results):
                assert result.status_code == 200, f"Request {i+1} failed with status {result.status_code}"

            print("✓ Server handles concurrent requests")
        except Exception as e:
            print(f"✗ Concurrent requests test failed: {e}")
            raise

    def run_all_tests(self):
        """Run all tests."""
        self.setup()
        try:
            self.test_health_check()
            self.test_websocket_endpoint()
            self.test_statistics_api()
            self.test_sample_files_listing()
            self.test_upload_functionality()
            self.test_batch_task_creation()
            self.test_concurrent_requests()
            print("\n✓ All tests passed!")
        except Exception as e:
            print(f"\n✗ Test failed: {e}")
            raise
        finally:
            self.teardown()

if __name__ == "__main__":
    tester = TestWebInterface()
    tester.run_all_tests()
