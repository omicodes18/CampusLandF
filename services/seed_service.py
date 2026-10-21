"""
services/seed_service.py
Populates realistic sample data matching the Stitch Blush Collegiate UI
when running the application locally so the board is immediately vibrant.
"""

from database import get_db
from werkzeug.security import generate_password_hash


def seed_demo_data_if_empty():
    """Seed demo accounts and lost & found posts if the database is currently empty."""
    db = get_db()
    user_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if user_count > 0:
        return

    # Create demo users
    hashed_student = generate_password_hash("StudentPass123")
    hashed_admin = generate_password_hash("AdminPass123")

    db.execute(
        "INSERT INTO users (name, email, password_hash, role, phone) VALUES (?, ?, ?, ?, ?)",
        ("Emma Clark", "student@campus.edu", hashed_student, "student", "555-0142"),
    )
    student_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    db.execute(
        "INSERT INTO users (name, email, password_hash, role, phone) VALUES (?, ?, ?, ?, ?)",
        ("Campus Safety Desk", "admin@campus.edu", hashed_admin, "admin", "555-0100"),
    )
    admin_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Sample lost & found items from Stitch UI design
    sample_items = [
        (
            "Black Wireless Headphones (Sony WH-1000XM4)",
            "Found on study carrel #14 on second floor. Left inside a protective matte carry pouch.",
            "Electronics",
            "found",
            "Science Library Desk",
            "2025-05-12",
            "open",
            admin_id,
            "lostfound@campus.edu",
            "555-0199",
        ),
        (
            "Pink Water Bottle (Hydro Flask 32oz)",
            "Decorated with university club stickers and a small studio ghibli enamel charm on the strap handle.",
            "Others",
            "lost",
            "Student Union Atrium",
            "2025-05-12",
            "open",
            student_id,
            "emma.c@campus.edu",
            "555-0142",
        ),
        (
            "University Student ID Card",
            "Name initials 'S. M.' with engineering department stamp. Stored securely at Campus Safety Kiosk.",
            "ID Cards & Documents",
            "found",
            "Central Quad Bench",
            "2025-05-11",
            "open",
            admin_id,
            "lostfound@campus.edu",
            "555-0100",
        ),
        (
            "Navy Blue Kånken Backpack",
            "Classic model with front pocket containing organic chemistry notebook and graphing calculator TI-84.",
            "Bags & Wallets",
            "lost",
            "Engineering Lab 204",
            "2025-05-11",
            "open",
            student_id,
            "emma.c@campus.edu",
            "555-0142",
        ),
        (
            "Silver Cat Charm Keychain (3 keys)",
            "Found near locker #82 after volleyball practice. Transferred to Rec Center reception desk.",
            "Keys",
            "found",
            "Rec Gym Locker",
            "2025-05-10",
            "open",
            admin_id,
            "recreation@campus.edu",
            "555-0188",
        ),
        (
            "Pastel Floral Bound Notebook (Calculus)",
            "Calculus II lecture notes, soft pink cover with wildflower motifs. Contains midterm preparation notes.",
            "Books & Stationery",
            "lost",
            "Humanities Hall 102",
            "2025-05-09",
            "open",
            student_id,
            "emma.c@campus.edu",
            "555-0142",
        ),
    ]

    for item in sample_items:
        db.execute(
            """
            INSERT INTO items (
                title, description, category, type, location, date_event, status, user_id, contact_email, contact_phone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            item,
        )

    # Add a sample notification for student
    db.execute(
        """
        INSERT INTO notifications (user_id, title, message, is_read)
        VALUES (?, ?, ?, 0)
        """,
        (student_id, "Welcome to Campus Lost & Found", "Welcome to the Campus Lost & Found Registry! File reports or claim items anytime."),
    )

    db.commit()
