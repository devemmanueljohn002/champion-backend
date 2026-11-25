from app.models import SchoolClass, Student, Examination, Question, ExaminationResult


def class_payload(row: SchoolClass, student_count: int | None = None):
    return {
        "id": row.id, "name": row.name, "category": row.category, "teacherId": row.teacherId,
        "teacher": ({"fullName": row.teacher.fullName} if row.teacher else None),
        "_count": {"students": student_count if student_count is not None else len(row.students)},
    }


def student_payload(row: Student, include_user: bool = True):
    result = {
        "id": row.id, "studentCode": row.studentCode, "fullName": row.fullName,
        "gender": row.gender, "photoUrl": row.photoUrl, "classId": row.classId,
        "isDemo": row.isDemo,
        "class": {"id": row.schoolClass.id, "name": row.schoolClass.name},
    }
    if include_user:
        result["user"] = {"active": row.user.active}
        result["active"] = row.user.active
    return result


def exam_payload(row: Examination, include_counts: bool = False):
    result = {
        "id": row.id, "title": row.title, "status": row.status.value,
        "classId": row.classId, "class": {"id": row.schoolClass.id, "name": row.schoolClass.name},
        "subjectId": row.subjectId,
        "subject": ({"id": row.subject.id, "name": row.subject.name} if row.subject else None),
        "roundId": row.roundId, "round": ({"id": row.round.id, "name": row.round.name, "type": row.round.type.value} if row.round else None),
        "durationMin": row.durationMin, "startsAt": row.startsAt, "endsAt": row.endsAt, "pausedAt": row.pausedAt,
        "actualStartedAt": row.actualStartedAt,
        "shuffleQuestions": row.shuffleQuestions, "shuffleOptions": row.shuffleOptions,
        "negativeMarking": row.negativeMarking, "passMark": row.passMark,
        "resultsPublished": row.resultsPublished,
    }
    if include_counts:
        result["_count"] = {"questions": len(row.questions), "sessions": len(row.sessions), "results": len(row.results)}
    return result


def question_admin_payload(row: Question):
    return {
        "id": row.id, "text": row.text, "type": row.type.value,
        "subjectId": row.subjectId, "subject": {"id": row.subject.id, "name": row.subject.name},
        "topicId": row.topicId, "topic": ({"id": row.topic.id, "name": row.topic.name} if row.topic else None),
        "classId": row.classId, "difficulty": row.difficulty.value, "marks": row.marks,
        "seconds": row.seconds, "explanation": row.explanation, "imageUrl": row.imageUrl,
        "status": row.status.value, "isDemo": row.isDemo,
        "options": [{"id": o.id, "label": o.label, "text": o.text, "isCorrect": o.isCorrect} for o in row.options],
    }


def result_payload(row: ExaminationResult):
    return {"id": row.id, "examId": row.examId, "studentId": row.studentId, "score": row.score,
            "total": row.total, "correct": row.correct, "incorrect": row.incorrect,
            "unanswered": row.unanswered, "timeSeconds": row.timeSeconds, "published": row.published}
