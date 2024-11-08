from CTFd.models import db
from sqlalchemy import inspect

def get_current_revision():
    return '1234'

def upgrade():
    bind = db.engine
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # live_challenge_users 테이블 생성
    if 'live_challenge_users' not in tables:
        db.create_all()

    # live_challenge 테이블 생성
    if 'live_challenge' not in tables:
        class LiveChallenge(db.Model):
            __tablename__ = "live_challenge"
            id = db.Column(
                db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), 
                primary_key=True
            )

        LiveChallenge.__table__.create(bind)

def downgrade():
    bind = db.engine
    LiveChallenge.__table__.drop(bind)
    LiveChallengeUsers.__table__.drop(bind)