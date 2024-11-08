from flask import Blueprint, render_template, request, abort
from sqlalchemy import inspect
from CTFd.models import Challenges, Users, db
from CTFd.utils.user import get_current_user, is_admin
from CTFd.utils.decorators import admins_only, authed_only
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import CHALLENGE_CLASSES, BaseChallenge
from CTFd.cache import cache


class LiveChallenge(Challenges):
    __tablename__ = "live_challenge"
    __mapper_args__ = {"polymorphic_identity": "live"}
    id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE"), primary_key=True
    )


class LiveChallengeUsers(db.Model):
    __tablename__ = "live_challenge_users"
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE")
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE")
    )


class LiveValueChallenge(BaseChallenge):
    id = "live"  
    name = "live"  
    templates = {  
        "create": "/plugins/live_challenges/assets/create.html",
        "update": "/plugins/live_challenges/assets/update.html",
        "view": "/plugins/live_challenges/assets/view.html",
    }
    scripts = {  
        "create": "/plugins/live_challenges/assets/create.js",
        "update": "/plugins/live_challenges/assets/update.js",
        "view": "/plugins/live_challenges/assets/view.js",
    }
    route = "/plugins/live_challenges/assets/"
    blueprint = Blueprint(
        "live_challenges",
        __name__,
        template_folder="templates",
        static_folder="assets",
        url_prefix="/api/v1/live_challenges"
    )
    challenge_model = LiveChallenge

    @classmethod
    def create(cls, request):
        data = request.form or request.get_json()
        
        challenge = cls.challenge_model(
            name=data.get("name"),
            description=data.get("description"),
            value=data.get("value"),
            category=data.get("category"),
            state=data.get("state"),
            type=data.get("type"),
        )

        db.session.add(challenge)
        db.session.flush()

        allowed_users = data.get("allowed_users", "").split(",")
        for user_id in allowed_users:
            if user_id.strip():
                user_challenge = LiveChallengeUsers(
                    challenge_id=challenge.id,
                    user_id=int(user_id.strip())
                )
                db.session.add(user_challenge)
        
        db.session.commit()
        return challenge

    @classmethod
    def read(cls, challenge):
        """
        사용자별 챌린지 접근 권한을 확인하고 챌린지 데이터를 반환합니다.
        """
        challenge = LiveChallenge.query.filter_by(id=challenge.id).first()
        if not challenge:
            return {
                "success": False,
                "errors": {"": "Challenge not found"}
            }

        # Admin이 아닌 경우 권한 확인
        if not is_admin():
            user = get_current_user()
            if not user:
                return {
                    "success": False,
                    "errors": {"": "Not logged in"}
                }

            # 사용자의 챌린지 접근 권한 확인
            allowed_user = LiveChallengeUsers.query.filter_by(
                challenge_id=challenge.id,
                user_id=user.id
            ).first()
            
            if not allowed_user:
                return {
                    "success": False,
                    "errors": {"": "You do not have access to this challenge"}
                }
        
        data = {
            "success": True,
            "data": {
                "id": challenge.id,
                "name": challenge.name,
                "value": challenge.value,
                "description": challenge.description,
                "category": challenge.category,
                "state": challenge.state,
                "max_attempts": challenge.max_attempts,
                "type": challenge.type,
                "type_data": {
                    "id": cls.id,
                    "name": cls.name,
                    "templates": cls.templates,
                    "scripts": cls.scripts,
                }
            }
        }

        # 관리자 엔드포인트에서는 사용자 목록과 현재 허용된 사용자 목록을 포함
        if request.endpoint and "admin" in request.endpoint:
            users = Users.query.filter_by(type="user", banned=False, hidden=False).all()
            data['data']['users'] = [{'id': user.id, 'name': user.name} for user in users]
            
            allowed_users = LiveChallengeUsers.query.filter_by(challenge_id=challenge.id).all()
            data['data']['allowed_users'] = [user.user_id for user in allowed_users]
            
        return data

    @classmethod
    def update(cls, challenge, request):
        data = request.form or request.get_json()

        for attr in ['name', 'description', 'value', 'category', 'state']:
            if attr in data:
                setattr(challenge, attr, data[attr])

        if "allowed_users" in data:
            LiveChallengeUsers.query.filter_by(challenge_id=challenge.id).delete()
            
            user_ids = data["allowed_users"].split(",")
            for user_id in user_ids:
                if user_id.strip():
                    new_user_challenge = LiveChallengeUsers(
                        challenge_id=challenge.id,
                        user_id=int(user_id.strip())
                    )
                    db.session.add(new_user_challenge)

        db.session.commit()
        return challenge

    @classmethod
    def solve(cls, user, team, challenge, request):
        allowed_user = LiveChallengeUsers.query.filter_by(
            challenge_id=challenge.id,
            user_id=user.id
        ).first()
        
        if not allowed_user:
            return False
            
        return super().solve(user, team, challenge, request)

    @classmethod
    def attempt(cls, challenge, request):
        user = get_current_user()
        if not user:
            return False

        allowed_user = LiveChallengeUsers.query.filter_by(
            challenge_id=challenge.id,
            user_id=user.id
        ).first()
        
        if not allowed_user:
            return False
            
        return True


@LiveValueChallenge.blueprint.route('/check_access/<int:challenge_id>', methods=['GET'])
@authed_only
def check_challenge_access(challenge_id):
    if is_admin():
        return {"success": True}
        
    user = get_current_user()
    
    allowed_user = LiveChallengeUsers.query.filter_by(
        challenge_id=challenge_id,
        user_id=user.id
    ).first()
    
    return {
        "success": allowed_user is not None
    }


@LiveValueChallenge.blueprint.route('/users', methods=['GET'])
@admins_only
def get_users():
    users = Users.query.filter_by(type="user", banned=False, hidden=False).all()
    return {
        'success': True,
        'data': [{'id': user.id, 'name': user.name} for user in users]
    }


def create_tables():
    if not inspect(db.engine).has_table("live_challenge_users"):
        LiveChallengeUsers.__table__.create(db.engine)
        
    if not inspect(db.engine).has_table("live_challenge"):
        LiveChallenge.__metadata__.create_all(db.engine)


def load(app):
    try:
        app.db.create_all()
        create_tables()
        
        CHALLENGE_CLASSES["live"] = LiveValueChallenge
        register_plugin_assets_directory(
            app, base_path="/plugins/live_challenges/assets/"
        )
        app.register_blueprint(LiveValueChallenge.blueprint)
    except Exception as e:
        print(f"Error loading live_challenges plugin: {e}")
        raise e