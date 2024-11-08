CTFd._internal.challenge.data = undefined;

CTFd._internal.challenge.renderer = CTFd.lib.markdown();

CTFd._internal.challenge.preRender = function() {};

CTFd._internal.challenge.render = function(markdown) {
    return CTFd._internal.challenge.renderer.render(markdown);
};

CTFd._internal.challenge.postRender = function() {
    // Check user access
    var challenge_id = parseInt(CTFd.lib.$("#challenge-id").val());

    CTFd.fetch("/api/v1/live_challenges/check_access/" + challenge_id, {
        method: "GET",
        credentials: "same-origin",
        headers: {
            "Accept": "application/json",
            "Content-Type": "application/json"
        },
    }).then(function(response) {
        if (!response.success) {
            // 권한이 없는 경우 에러 메시지 표시하고 챌린지 입력 비활성화
            CTFd.lib.$("#challenge-window").html(
                '<div class="alert alert-danger">You do not have permission to view this challenge.</div>'
            );
            CTFd.lib.$("#challenge-input").prop("disabled", true);
            CTFd.lib.$("#challenge-submit").prop("disabled", true);
        }
    });
};

CTFd._internal.challenge.submit = function(preview) {
    var challenge_id = parseInt(CTFd.lib.$("#challenge-id").val());
    var submission = CTFd.lib.$("#challenge-input").val();

    var body = {
        challenge_id: challenge_id,
        submission: submission
    };
    var params = {};
    if (preview) {
        params["preview"] = true;
    }

    return CTFd.api.post_challenge_attempt(params, body).then(function(response) {
        if (response.status === 429) {
            // User was ratelimited but process response
            return response;
        }
        if (response.status === 403) {
            // User is not logged in or CTF is paused.
            return response;
        }
        return response;
    });
};