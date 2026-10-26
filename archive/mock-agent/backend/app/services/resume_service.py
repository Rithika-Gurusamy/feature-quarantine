import io
import re
from typing import Tuple, List, Optional
from pypdf import PdfReader
from docx import Document
from app.models.schemas import CandidateProfile, CandidateProject

class ResumeParserService:
    @staticmethod
    def extract_text(file_bytes: bytes, filename: str) -> str:
        filename_lower = filename.lower()
        if filename_lower.endswith(".pdf"):
            return ResumeParserService._extract_pdf(file_bytes)
        elif filename_lower.endswith(".docx"):
            return ResumeParserService._extract_docx(file_bytes)
        elif filename_lower.endswith(".txt"):
            return file_bytes.decode("utf-8", errors="ignore").strip()
        else:
            raise ValueError(f"Unsupported file format: {filename}. Supported formats are .pdf, .docx, and .txt.")

    @staticmethod
    def _extract_pdf(file_bytes: bytes) -> str:
        reader = PdfReader(io.BytesIO(file_bytes))
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts).strip()

    @staticmethod
    def _extract_docx(file_bytes: bytes) -> str:
        doc = Document(io.BytesIO(file_bytes))
        text_parts = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    text_parts.append(row_text)
        return "\n".join(text_parts).strip()

    @staticmethod
    def detect_candidate_name(resume_text: str, filename: str) -> str:
        lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
        for line in lines[:5]:
            # Filter out common resume headers
            if re.search(r"resume|curriculum|vitae|email|phone|contact|github|linkedin|summary|skills", line, re.IGNORECASE):
                continue
            words = line.split()
            if 2 <= len(words) <= 4 and all(re.match(r"^[A-Za-z\.\'-]+$", w) for w in words):
                return line.title()

        # Fallback to filename without extension
        clean_fn = re.sub(r"[\._\-]*(resume|cv)[\._\-]*", "", filename, flags=re.IGNORECASE)
        clean_fn = re.sub(r"\.[a-zA-Z0-9]+$", "", clean_fn).strip()
        if clean_fn:
            words = re.split(r"[\s_\-]+", clean_fn)
            return " ".join(w.capitalize() for w in words if w)

        return "Candidate"

    @classmethod
    def extract_candidate_profile(cls, resume_text: str, filename: str) -> CandidateProfile:
        """
        Parses resume text into a rich structured CandidateProfile JSON memory.
        """
        name = cls.detect_candidate_name(resume_text, filename)

        # Detect email
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", resume_text)
        email = email_match.group(0) if email_match else None

        # Detect candidate title/role
        title = "Software Engineer"
        lines = [l.strip() for l in resume_text.splitlines() if l.strip()]
        for line in lines[1:6]:
            if re.search(r"engineer|developer|architect|lead|specialist|manager|scientist|analyst", line, re.IGNORECASE):
                if not re.search(r"email|phone|github|linkedin|@", line, re.IGNORECASE):
                    title = line
                    break

        # Extract Skills
        skills = cls._extract_skills(resume_text)

        # Extract Projects
        projects = cls._extract_projects(resume_text)

        # Extract Summary
        summary = cls._extract_summary(resume_text)

        # Experience Highlights
        highlights = cls._extract_highlights(resume_text)

        return CandidateProfile(
            candidate_name=name,
            title=title,
            email=email,
            summary=summary,
            skills=skills,
            projects=projects,
            experience_highlights=highlights,
            topics_covered=[],
            evaluated_strengths=[]
        )

    @staticmethod
    def _extract_skills(text: str) -> List[str]:
        common_tech = [
            "Python", "FastAPI", "Django", "Flask", "TypeScript", "JavaScript", "React",
            "Next.js", "Node.js", "Go", "Golang", "Java", "C++", "Rust", "PostgreSQL",
            "MySQL", "Redis", "MongoDB", "Cassandra", "Apache Kafka", "Kafka", "RabbitMQ",
            "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Terraform", "GraphQL",
            "REST", "gRPC", "Elasticsearch", "Airflow", "PyTorch", "TensorFlow", "Spark"
        ]
        found = []
        for tech in common_tech:
            pattern = r"\b" + re.escape(tech) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                if tech == "Golang":
                    tech = "Go"
                if tech not in found:
                    found.append(tech)
        return found if found else ["System Design", "Backend Engineering", "REST APIs"]

    @staticmethod
    def _extract_projects(text: str) -> List[CandidateProject]:
        projects: List[CandidateProject] = []
        
        # Look for numbered or bulleted projects
        project_blocks = re.split(r"\n(?=\d+\.|\bProject:|\bKey Projects?:)", text)
        for block in project_blocks:
            lines = [l.strip() for l in block.splitlines() if l.strip()]
            if not lines:
                continue
            first_line = lines[0]
            if re.search(r"project|pipeline|gateway|service|platform|system|application|api", first_line, re.IGNORECASE):
                name = re.sub(r"^(\d+\.|\bProject:\s*)", "", first_line).strip(" :-\t")
                desc = " ".join(lines[1:4]) if len(lines) > 1 else first_line
                
                # Check for metrics
                metric_match = re.search(r"(\d+[\d,]*\s*(?:req/s|requests/sec|events/sec|users|%|ms|latency|throughput))", block, re.IGNORECASE)
                metric = metric_match.group(0) if metric_match else ""

                # Extract technologies in this block
                techs = [t for t in ["Kafka", "FastAPI", "Redis", "PostgreSQL", "Docker", "AWS", "React", "Node.js", "Python"] if re.search(r"\b" + t + r"\b", block, re.IGNORECASE)]

                projects.append(CandidateProject(
                    name=name if name else "Technical Project",
                    technologies=techs,
                    metrics=metric,
                    description=desc
                ))

        if not projects:
            projects.append(CandidateProject(
                name="Distributed Real-Time System",
                technologies=["FastAPI", "Kafka", "PostgreSQL"],
                metrics="High-throughput",
                description="Designed high-throughput real-time backend architecture."
            ))

        return projects[:4]

    @staticmethod
    def _extract_summary(text: str) -> str:
        match = re.search(r"(?:Summary|About|Profile)[:\s]*\n?([^\n]+(?:\n[^\n]+){1,3})", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return lines[1] if len(lines) > 1 else "Experienced software engineer."

    @staticmethod
    def _extract_highlights(text: str) -> List[str]:
        bullets = []
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("-") or line.startswith("•") or line.startswith("*"):
                clean = line.lstrip("-•* ").strip()
                if len(clean) > 20:
                    bullets.append(clean)
        return bullets[:5]

resume_service = ResumeParserService()
