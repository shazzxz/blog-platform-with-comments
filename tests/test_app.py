import json
import tempfile
import unittest
from pathlib import Path

from backend.app import create_app


class BlogApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "DATABASE": str(Path(self.tmp.name) / "test.db"), "SECRET_KEY": "test-key"})
        self.client = self.app.test_client()
        self.a = self.register("Writer A", "writer-a@example.test")
        self.b = self.register("Writer B", "writer-b@example.test")

    def tearDown(self):
        self.tmp.cleanup()

    def register(self, name, email):
        response = self.client.post("/api/auth/register", json={"name": name, "email": email, "password": "safe-pass-123"})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def auth(self, account):
        return {"Authorization": "Bearer " + account["token"]}

    def story(self, account):
        response = self.client.post("/api/posts", headers=self.auth(account), json={
            "title": "A test story",
            "excerpt": "Short introduction",
            "category": "Technology",
            "body": "This is a test story with enough content to satisfy the minimum length."
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["post"]

    def test_health_and_authentication(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        response = self.client.get("/api/auth/me", headers=self.auth(self.a))
        self.assertEqual(response.get_json()["user"]["email"], "writer-a@example.test")

    def test_post_ownership_and_comments(self):
        story = self.story(self.a)
        response = self.client.patch("/api/posts/" + str(story["id"]), headers=self.auth(self.b), json={"title": "Hijack"})
        self.assertEqual(response.status_code, 403)
        comment = self.client.post("/api/posts/" + str(story["id"]) + "/comments", headers=self.auth(self.b), json={"body": "A thoughtful comment"})
        self.assertEqual(comment.status_code, 201)
        comment_id = comment.get_json()["comment"]["id"]
        self.assertEqual(self.client.delete("/api/comments/" + str(comment_id), headers=self.auth(self.a)).status_code, 403)
        self.assertEqual(self.client.delete("/api/comments/" + str(comment_id), headers=self.auth(self.b)).status_code, 200)

    def test_search_and_delete(self):
        story = self.story(self.a)
        response = self.client.get("/api/posts?search=test&category=Technology")
        self.assertEqual(len(response.get_json()["posts"]), 1)
        self.assertEqual(self.client.delete("/api/posts/" + str(story["id"]), headers=self.auth(self.a)).status_code, 200)
        self.assertEqual(self.client.get("/api/posts/" + str(story["id"])).status_code, 404)

    def test_invalid_duplicate_and_password(self):
        self.assertEqual(self.client.post("/api/auth/register", json={"name": "X", "email": "bad", "password": "123"}).status_code, 400)
        response = self.client.post("/api/auth/register", json={"name": "Writer A", "email": "writer-a@example.test", "password": "safe-pass-123"})
        self.assertEqual(response.status_code, 409)


if __name__ == "__main__":
    unittest.main()
