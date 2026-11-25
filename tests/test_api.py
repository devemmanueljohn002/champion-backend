def test_health_and_authentication_boundary(client):
    assert client.get("/healthz").status_code == 200
    response = client.get("/api/v1/admin/overview")
    assert response.status_code == 401


def test_admin_student_exam_workflow_and_answer_secrecy(client):
    login = client.post("/api/v1/auth/login", json={"loginId": "test-admin", "password": "Strong-Test-Password-123"})
    assert login.status_code == 200
    assert login.json()["role"] == "ADMIN"

    school_class = client.post("/api/v1/admin/classes", json={"name": "JSS1", "category": "JUNIOR"})
    assert school_class.status_code == 201, school_class.text
    class_id = school_class.json()["id"]

    subject = client.post("/api/v1/admin/subjects", json={"name": "Mathematics"})
    assert subject.status_code == 201, subject.text
    subject_id = subject.json()["id"]

    question = client.post("/api/v1/admin/questions", json={
        "text": "What is 1 + 1?", "subjectId": subject_id, "classId": class_id,
        "difficulty": "EASY", "marks": 2,
        "options": [
            {"label": "A", "text": "2", "isCorrect": True},
            {"label": "B", "text": "3", "isCorrect": False},
            {"label": "C", "text": "4", "isCorrect": False},
            {"label": "D", "text": "5", "isCorrect": False},
        ],
    })
    assert question.status_code == 201, question.text
    correct_option_id = next(option["id"] for option in question.json()["options"] if option["isCorrect"])

    student = client.post("/api/v1/admin/students", json={
        "studentCode": "STU-001", "fullName": "Sample Student", "classId": class_id,
        "password": "Student-Password-123",
    })
    assert student.status_code == 201, student.text
    student_id = student.json()["id"]
    round_response = client.post("/api/v1/admin/rounds", json={"name": "Preliminary", "type": "PRELIM", "orderNo": 1, "advanceCount": 1})
    assert round_response.status_code == 201, round_response.text
    round_id = round_response.json()["id"]
    participants = client.post(f"/api/v1/admin/rounds/{round_id}/participants", json={"studentIds": [student_id]})
    assert participants.status_code == 201, participants.text

    from datetime import datetime, timedelta
    now = datetime.now()
    exam = client.post("/api/v1/admin/examinations", json={
        "title": "Mathematics Test", "classId": class_id, "roundId": round_id, "durationMin": 20,
        "startsAt": (now - timedelta(minutes=2)).isoformat(),
        "endsAt": (now + timedelta(minutes=30)).isoformat(), "questionCount": 1,
    })
    assert exam.status_code == 201, exam.text
    exam_id = exam.json()["id"]
    assert client.patch(f"/api/v1/admin/examinations/{exam_id}", json={"action": "GO_LIVE"}).status_code == 200

    student_client = client.__class__(client.app)
    student_login = student_client.post("/api/v1/auth/login", json={"loginId": "STU-001", "password": "Student-Password-123"})
    assert student_login.status_code == 200

    before_start = student_client.get(f"/api/v1/student/exams/{exam_id}")
    assert before_start.status_code == 200
    assert before_start.json()["submitted"] is False
    assert before_start.json()["questions"] == []

    start = student_client.post(f"/api/v1/student/exams/{exam_id}", json={"action": "start"})
    assert start.status_code == 200, start.text
    active = student_client.get(f"/api/v1/student/exams/{exam_id}")
    assert active.status_code == 200
    paused = client.patch(f"/api/v1/admin/examinations/{exam_id}", json={"action": "PAUSE"})
    assert paused.status_code == 200
    paused_view = student_client.get(f"/api/v1/student/exams/{exam_id}")
    assert paused_view.json()["paused"] is True
    blocked_save = student_client.post(f"/api/v1/student/exams/{exam_id}", json={"action": "visibility"})
    assert blocked_save.status_code == 409
    resumed = client.patch(f"/api/v1/admin/examinations/{exam_id}", json={"action": "RESUME"})
    assert resumed.status_code == 200
    active = student_client.get(f"/api/v1/student/exams/{exam_id}")
    assert active.status_code == 200
    public_question = active.json()["questions"][0]
    assert "isCorrect" not in str(public_question)
    assert all("isCorrect" not in option for option in public_question["options"])

    save = student_client.post(f"/api/v1/student/exams/{exam_id}", json={
        "action": "save", "questionId": public_question["id"], "optionId": correct_option_id, "flagged": False,
    })
    assert save.status_code == 200, save.text
    submit = student_client.post(f"/api/v1/student/exams/{exam_id}", json={"action": "submit"})
    assert submit.status_code == 200, submit.text

    publish = client.patch(f"/api/v1/admin/examinations/{exam_id}", json={"action": "PUBLISH_RESULTS"})
    assert publish.status_code == 200
    result = student_client.get(f"/api/v1/student/exams/{exam_id}")
    assert result.json()["submitted"] is True
    assert result.json()["result"]["published"] is True
    assert result.json()["result"]["score"] == 2
    leaderboard = student_client.get(f"/api/v1/leaderboard?roundId={round_id}")
    assert leaderboard.status_code == 200
    assert leaderboard.json()["classes"][0]["className"] == "JSS1"
    assert leaderboard.json()["classes"][0]["avgPercent"] == 100.0
    scores = client.post("/api/v1/admin/class-scores/recalculate", json={"roundId": round_id})
    assert scores.status_code == 200, scores.text
    snapshot = client.post(f"/api/v1/admin/rounds/{round_id}/leaderboard/generate")
    assert snapshot.status_code == 200, snapshot.text
    saved = client.get(f"/api/v1/admin/leaderboards?roundId={round_id}")
    assert saved.status_code == 200
    assert len(saved.json()) == 2


def test_teacher_account_and_class_assignment(client):
    login = client.post("/api/v1/auth/login", json={"loginId": "test-admin", "password": "Strong-Test-Password-123"})
    assert login.status_code == 200
    school_class = client.post("/api/v1/admin/classes", json={"name": "SS1", "category": "SENIOR"})
    assert school_class.status_code == 201
    teacher = client.post("/api/v1/admin/teachers", json={
        "loginId": "teacher-01", "fullName": "Test Teacher", "password": "Teacher-Password-123",
    })
    assert teacher.status_code == 201, teacher.text
    assigned = client.patch(f"/api/v1/admin/classes/{school_class.json()['id']}", json={"teacherId": teacher.json()['id']})
    assert assigned.status_code == 200, assigned.text

    from fastapi.testclient import TestClient
    teacher_client = TestClient(client.app)
    teacher_login = teacher_client.post("/api/v1/auth/login", json={"loginId": "teacher-01", "password": "Teacher-Password-123"})
    assert teacher_login.status_code == 200
    dashboard = teacher_client.get("/api/v1/teacher/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()['teacher']['fullName'] == 'Test Teacher'
    assert dashboard.json()['classes'][0]['name'] == 'SS1'


def test_csv_question_preview_import_duplicate_and_validation(client):
    login = client.post("/api/v1/auth/login", json={"loginId": "test-admin", "password": "Strong-Test-Password-123"})
    assert login.status_code == 200

    csv_text = (
        "question_number,class,subject,question_type,question,option_a,option_b,option_c,option_d,"
        "correct_answer,difficulty,status,marks\r\n"
        "1,JSS 1,Mathematics,MCQ,What is 5 + 5?,8,9,10,11,C,EASY,APPROVED,1\r\n"
        "2,JSS 1,Mathematics,MCQ,What is 5 + 5?,8,9,10,11,C,EASY,APPROVED,1\r\n"
        "3,JSS 1,Mathematics,MCQ,,8,9,10,11,C,EASY,APPROVED,1\r\n"
    )

    preview = client.post(
        "/api/v1/admin/questions/import-csv",
        files={"file": ("questions.csv", csv_text.encode("utf-8-sig"), "text/csv")},
        data={"mode": "preview"},
    )
    assert preview.status_code == 200
    assert preview.json()["invalid"] == 3

    school_class = client.post("/api/v1/admin/classes", json={"name": "JSS 1", "category": "JUNIOR"})
    assert school_class.status_code == 201
    subject = client.post("/api/v1/admin/subjects", json={"name": "Mathematics"})
    assert subject.status_code == 201

    preview = client.post(
        "/api/v1/admin/questions/import-csv",
        files={"file": ("questions.csv", csv_text.encode("utf-8-sig"), "text/csv")},
        data={"mode": "preview"},
    )
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["total"] == 3
    assert payload["valid"] == 2
    assert payload["invalid"] == 1
    assert payload["duplicates"] == 1

    first_row = payload["rows"][0]["row"]
    imported = client.post(
        "/api/v1/admin/questions/import-csv",
        files={"file": ("questions.csv", csv_text.encode("utf-8-sig"), "text/csv")},
        data={"mode": "import", "selectedRows": str(first_row)},
    )
    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result["successfullyImported"] == 1
    assert result["duplicates"] == 0
    assert len(client.get("/api/v1/admin/questions").json()) == 1


def test_csv_question_import_rejects_unauthorized_and_non_csv(client):
    unauthorized = client.post(
        "/api/v1/admin/questions/import-csv",
        files={"file": ("questions.txt", b"not a csv", "text/plain")},
        data={"mode": "preview"},
    )
    assert unauthorized.status_code == 401

    login = client.post("/api/v1/auth/login", json={"loginId": "test-admin", "password": "Strong-Test-Password-123"})
    assert login.status_code == 200
    non_csv = client.post(
        "/api/v1/admin/questions/import-csv",
        files={"file": ("questions.txt", b"not a csv", "text/plain")},
        data={"mode": "preview"},
    )
    assert non_csv.status_code == 400

    malformed = client.post(
        "/api/v1/admin/questions/import-csv",
        files={"file": ("questions.csv", b"wrong,header\r\n1,x\r\n", "text/csv")},
        data={"mode": "preview"},
    )
    assert malformed.status_code == 400
