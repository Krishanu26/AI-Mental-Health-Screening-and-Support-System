import unittest
from unittest.mock import patch
from backend.assessment import create_assessment_document,score_responses
from backend.app import app

class ProjectTests(unittest.TestCase):
 def setUp(self):self.client=app.test_client()
 def test_question_bank(self):self.assertEqual(len(self.client.get("/api/questions").get_json()["questions"]),21)
 def test_score_boundaries(self):
  for score,band in [(13,"Minimal Depression"),(14,"Mild Depression"),(19,"Mild Depression"),(20,"Moderate Depression"),(28,"Moderate Depression"),(29,"Severe Depression")]:
   values=[];left=score
   for _ in range(21):v=min(3,left);values.append(v);left-=v
   self.assertEqual(score_responses(values),(score,band))
 def test_invalid_answers(self):
  for values in ([0]*20,[True]+[0]*20,["0"]+[0]*20,[4]+[0]*20):
   with self.assertRaises(ValueError):score_responses(values)
 def test_research_requires_storage(self):
  with self.assertRaises(ValueError):create_assessment_document([0]*21,False,True)
 def test_stored_assessment_requires_user(self):
  with self.assertRaises(ValueError):create_assessment_document([0]*21,True,False)
 def test_user_scoped_research_consent(self):
  d=create_assessment_document([0]*21,True,True,"user-1")
  self.assertEqual(d["user_id"],"user-1");self.assertIn("raw_responses_for_ml",d)
 def test_ephemeral_assessment(self):
  d=create_assessment_document([0]*21,False,False)
  self.assertNotIn("user_id",d);self.assertNotIn("feedback_token",d)
 def test_storage_endpoint_requires_auth(self):
  r=self.client.post("/api/assessment",json={"responses":[0]*21,"storage_consent":True})
  self.assertEqual(r.status_code,401)
 def test_ephemeral_endpoint_works(self):
  r=self.client.post("/api/assessment",json={"responses":[0]*21})
  self.assertEqual(r.status_code,201);self.assertFalse(r.get_json()["saved"])
 def test_history_requires_auth(self):self.assertEqual(self.client.get("/api/assessments").status_code,401)
 def test_admin_requires_auth(self):self.assertEqual(self.client.get("/api/admin/analytics").status_code,401)
 def test_chat_history_requires_auth(self):self.assertEqual(self.client.get("/api/chat/history").status_code,401)

if __name__=="__main__":unittest.main()
