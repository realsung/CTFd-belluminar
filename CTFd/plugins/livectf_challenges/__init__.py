from flask import Blueprint, abort
from CTFd.models import Challenges, Users, db
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.challenges import CHALLENGE_CLASSES, BaseChallenge
from CTFd.plugins.migrations import upgrade
from CTFd.utils.user import get_current_user
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declared_attr

class LiveCTFChallenge(Challenges):
    __mapper_args__ = {
        "polymorphic_identity": "livectf"
    }
    
    @declared_attr
    def id(cls):
        return db.Column(
            db.Integer, 
            db.ForeignKey("challenges.id", ondelete="CASCADE"), 
            primary_key=True,
            extend_existing=True
        )
    
class LiveCTFAccess(db.Model):
    __tablename__ = "live_ctf_access"
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(
        db.Integer, db.ForeignKey("challenges.id", ondelete="CASCADE")
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE")
    )

class LiveCTFValueChallenge(BaseChallenge):
    id = "livectf"
    name = "livectf"
    templates = {
        "create": "/plugins/livectf_challenges/assets/create.html",
        "update": "/plugins/livectf_challenges/assets/update.html",
        "view": "/plugins/livectf_challenges/assets/view.html",
    }
    scripts = {
        "create": "/plugins/livectf_challenges/assets/create.js",
        "update": "/plugins/livectf_challenges/assets/update.js",
        "view": "/plugins/livectf_challenges/assets/view.js",
    }
    route = "/plugins/livectf_challenges/assets/"
    blueprint = Blueprint(
        "livectf_challenges",
        __name__,
        template_folder="templates",
        static_folder="assets",
    )
    challenge_model = LiveCTFChallenge

    @classmethod
    def read(cls, challenge):
        """
        challenge 데이터를 프론트엔드에서 처리할 수 있는 형식으로 변환
        """
        challenge = LiveCTFChallenge.query.filter_by(id=challenge.id).first()
        if not challenge:
            abort(404)
            
        # 현재 사용자가 접근 권한이 있는지 확인
        current_user = get_current_user()
        if not current_user:
            abort(403)
            
        access = LiveCTFAccess.query.filter_by(
            challenge_id=challenge.id,
            user_id=current_user.id
        ).first()
        
        if not access and not current_user.type == "admin":  # 관리자는 항상 접근 가능
            abort(403)

        data = {
            "id": challenge.id,
            "name": challenge.name,
            "value": challenge.value,
            "description": challenge.description,
            "connection_info": challenge.connection_info,
            "next_id": challenge.next_id,
            "category": challenge.category,
            "state": challenge.state,
            "max_attempts": challenge.max_attempts,
            "type": challenge.type,
            "type_data": {
                "id": cls.id,
                "name": cls.name,
                "templates": cls.templates,
                "scripts": cls.scripts,
            },
        }
        return data

    @classmethod
    def update(cls, challenge, request):
        """
        Challenge 정보 업데이트 및 접근 권한 설정
        """
        data = request.form or request.get_json()

        # 기본 challenge 정보 업데이트
        for attr, value in data.items():
            if attr != "authorized_users":
                setattr(challenge, attr, value)

        # 사용자 접근 권한 업데이트
        if "authorized_users" in data:
            # 기존 접근 권한 삭제
            LiveCTFAccess.query.filter_by(challenge_id=challenge.id).delete()
            
            # 새로운 접근 권한 추가
            authorized_users = data["authorized_users"].split(",")
            for username in authorized_users:
                username = username.strip()
                if username:  # 빈 문자열 체크
                    user = Users.query.filter_by(name=username).first()
                    if user:
                        access = LiveCTFAccess(
                            challenge_id=challenge.id,
                            user_id=user.id
                        )
                        db.session.add(access)

        db.session.commit()
        return challenge

    @classmethod
    def attempt(cls, challenge, request):
        """
        사용자 제출 시도 확인
        """
        current_user = get_current_user()
        if not current_user:
            abort(403)
            
        access = LiveCTFAccess.query.filter_by(
            challenge_id=challenge.id,
            user_id=current_user.id
        ).first()
        
        if not access and not current_user.type == "admin":
            abort(403)
            
        return super().attempt(challenge, request)

def load(app):
    # 데이터베이스 테이블이 이미 존재하는지 확인
    db.create_all()
    
    # Challenge 클래스 등록
    CHALLENGE_CLASSES["livectf"] = LiveCTFValueChallenge
    
    # 에셋 디렉토리 등록
    register_plugin_assets_directory(
        app, base_path="/plugins/livectf_challenges/assets/"
    )