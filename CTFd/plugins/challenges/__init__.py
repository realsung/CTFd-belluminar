from flask import Blueprint

from CTFd.utils.user import get_current_team

from CTFd.models import (
    ChallengeFiles,
    Challenges,
    Fails,
    Flags,
    Hints,
    Solves,
    Tags,
    Awards,
    db,
)

from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.flags import FlagException, get_flag_class
from CTFd.utils.uploads import delete_file
from CTFd.utils.user import get_ip
from sqlalchemy import func
import datetime


class BaseChallenge(object):
    id = None
    name = None
    templates = {}
    scripts = {}
    challenge_model = Challenges

    @classmethod
    def create(cls, request):
        """
        This method is used to process the challenge creation request.

        :param request:
        :return:
        """
        data = request.form or request.get_json()

        challenge = cls.challenge_model(**data)

        db.session.add(challenge)
        db.session.commit()

        return challenge

    @classmethod
    def read(cls, challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.

        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """

        data = {
            "id": challenge.id,
            "name": challenge.name,
            "value": challenge.value,
            "description": challenge.description,
            "attribution": challenge.attribution,
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
    
        team = get_current_team()
        if team and team.id == challenge.id:
            data["state"] = "hidden"

        return data

    @classmethod
    def update(cls, challenge, request):
        """
        This method is used to update the information associated with a challenge. This should be kept strictly to the
        Challenges table and any child tables.

        :param challenge:
        :param request:
        :return:
        """
        data = request.form or request.get_json()
        for attr, value in data.items():
            setattr(challenge, attr, value)

        db.session.commit()
        return challenge

    @classmethod
    def delete(cls, challenge):
        """
        This method is used to delete the resources used by a challenge.

        :param challenge:
        :return:
        """
        Fails.query.filter_by(challenge_id=challenge.id).delete()
        Solves.query.filter_by(challenge_id=challenge.id).delete()
        Flags.query.filter_by(challenge_id=challenge.id).delete()
        files = ChallengeFiles.query.filter_by(challenge_id=challenge.id).all()
        for f in files:
            delete_file(f.id)
        ChallengeFiles.query.filter_by(challenge_id=challenge.id).delete()
        Tags.query.filter_by(challenge_id=challenge.id).delete()
        Hints.query.filter_by(challenge_id=challenge.id).delete()
        Challenges.query.filter_by(id=challenge.id).delete()
        cls.challenge_model.query.filter_by(id=challenge.id).delete()
        db.session.commit()

    @classmethod
    def attempt(cls, challenge, request):
        """
        This method is used to check whether a given input is right or wrong. It does not make any changes and should
        return a boolean for correctness and a string to be shown to the user. It is also in charge of parsing the
        user's input from the request itself.

        :param challenge: The Challenge object from the database
        :param request: The request the user submitted
        :return: (boolean, string)
        """
        data = request.form or request.get_json()
        submission = data["submission"].strip()
        flags = Flags.query.filter_by(challenge_id=challenge.id).all()
        for flag in flags:
            try:
                if get_flag_class(flag.type).compare(flag, submission):
                    return True, "Correct"
            except FlagException as e:
                return False, str(e)
        return False, "Incorrect"

    @classmethod
    def solve(cls, user, team, challenge, request):
        """
        This method is used to insert Solves into the database in order to mark a challenge as solved.

        :param user: The User object from the database
        :param team: The Team object from the database
        :param challenge: The Challenge object from the database
        :param request: The request the user submitted
        :return:
        """
        data = request.form or request.get_json()
        submission = data["submission"].strip()

        # After solving, implement the custom logic
        if team:  # Ensure that team is not None
            # Check if the team is solving their own challenge
            if team.id == challenge.id:
                # Create an Award with negative value to negate the points
                # award = Awards(
                #     user_id=user.id,
                #     team_id=team.id,
                #     name='No points for solving own challenge',
                #     value=-challenge.value,
                #     description='No points awarded for solving your own challenge',
                #     category=challenge.category,
                # )
                fail = Fails(
                    user_id=user.id,
                    team_id=team.id if team else None,
                    challenge_id=challenge.id,
                    ip=get_ip(request),
                    provided=submission,
                )
                db.session.add(fail)
                db.session.commit()
            else:
                solve = Solves(
                    user_id=user.id,
                    team_id=team.id if team else None,
                    challenge_id=challenge.id,
                    ip=get_ip(req=request),
                    provided=submission,
                )
                db.session.add(solve)
                db.session.commit()

        # Now, award points to the author team if thresholds are met
        # Get the number of unique teams that have solved the challenge
        team_solve_count = (
            db.session.query(func.count(func.distinct(Solves.team_id)))
            .filter_by(challenge_id=challenge.id)
            .scalar()
        )

        # Define the award thresholds
        award_thresholds = [
            (0, 0),
            (1, 200),
            (2, 500),
            (3, 800),
            (4, 1200),
            (5, 1600),
            (6, 2000),
            (7, 1600),
            (8, 1200),
            (9, 800),
            (10, 500),
            (11, 200),
        ]

        # Check if the current team_solve_count matches any threshold
        for threshold, points in award_thresholds:
            if team_solve_count == threshold:
                # Check if the author team has already received an Award for this threshold
                award_description = f'Bonus'
                existing_award = Awards.query.filter_by(
                    team_id=challenge.id,
                    description=award_description,
                ).first()
                if not existing_award:
                    # Award the points to the author team
                    award = Awards(
                        user_id=None,
                        team_id=challenge.id,
                        type="standard",
                        name='Bonus 🩸',
                        description=award_description,
                        icon="crown",
                        value=points,
                        date=datetime.datetime.utcnow(),
                        category=challenge.category,
                        requirements={"challenge_id": challenge.id},
                    )
                    db.session.add(award)
                    db.session.commit()
                break  # Exit the loop since we've handled the current threshold


    @classmethod
    def fail(cls, user, team, challenge, request):
        """
        This method is used to insert Fails into the database in order to mark an answer incorrect.

        :param team: The Team object from the database
        :param chal: The Challenge object from the database
        :param request: The request the user submitted
        :return:
        """
        data = request.form or request.get_json()
        submission = data["submission"].strip()
        wrong = Fails(
            user_id=user.id,
            team_id=team.id if team else None,
            challenge_id=challenge.id,
            ip=get_ip(request),
            provided=submission,
        )
        db.session.add(wrong)
        db.session.commit()


class CTFdStandardChallenge(BaseChallenge):
    id = "standard"  # Unique identifier used to register challenges
    name = "standard"  # Name of a challenge type
    templates = {  # Templates used for each aspect of challenge editing & viewing
        "create": "/plugins/challenges/assets/create.html",
        "update": "/plugins/challenges/assets/update.html",
        "view": "/plugins/challenges/assets/view.html",
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        "create": "/plugins/challenges/assets/create.js",
        "update": "/plugins/challenges/assets/update.js",
        "view": "/plugins/challenges/assets/view.js",
    }
    # Route at which files are accessible. This must be registered using register_plugin_assets_directory()
    route = "/plugins/challenges/assets/"
    # Blueprint used to access the static_folder directory.
    blueprint = Blueprint(
        "standard", __name__, template_folder="templates", static_folder="assets"
    )
    challenge_model = Challenges


def get_chal_class(class_id):
    """
    Utility function used to get the corresponding class from a class ID.

    :param class_id: String representing the class ID
    :return: Challenge class
    """
    cls = CHALLENGE_CLASSES.get(class_id)
    if cls is None:
        raise KeyError
    return cls


"""
Global dictionary used to hold all the Challenge Type classes used by CTFd. Insert into this dictionary to register
your Challenge Type.
"""
CHALLENGE_CLASSES = {"standard": CTFdStandardChallenge}


def load(app):
    register_plugin_assets_directory(app, base_path="/plugins/challenges/assets/")
