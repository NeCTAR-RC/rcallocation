#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Exceptions raised by the service and mapped to HTTP responses.

The response bodies reproduce what Django REST Framework produced in the
old nectar-dashboard API, because python-nectarallocationclient and other
consumers surface them to users unchanged.
"""


class RcAllocationException(Exception):
    status_code = 500
    detail = "A server error occurred."

    def __init__(self, detail=None):
        if detail is not None:
            self.detail = detail
        super().__init__(self.detail)

    def body(self):
        return {"detail": self.detail}


class ValidationError(RcAllocationException):
    """A 400 whose body is the DRF style error structure.

    ``messages`` is either a dict of ``{field: [messages]}`` (with
    ``non_field_errors`` for whole-object errors) or a plain list of
    messages, exactly as DRF serialised ``serializers.ValidationError``.
    """

    status_code = 400

    def __init__(self, messages):
        self.messages = messages
        super().__init__(str(messages))

    def body(self):
        return self.messages


class ActionError(RcAllocationException):
    """A 400 for an action precondition, body ``{"error": message}``."""

    status_code = 400

    def __init__(self, message):
        self.message = message
        super().__init__(message)

    def body(self):
        return {"error": self.message}


class WarningsError(RcAllocationException):
    """A 409 carrying approver sanity check warnings.

    Raised when a write is attempted with ``ignore_warnings`` false and the
    checkers produced warnings. ``warnings`` is a list of
    ``{"code": ..., "message": ...}`` dicts.
    """

    status_code = 409

    def __init__(self, warnings):
        self.warnings = warnings
        super().__init__("Request has warnings")

    def body(self):
        return {"warnings": self.warnings}


class NotAuthenticated(RcAllocationException):
    status_code = 401
    detail = "Authentication credentials were not provided."


class InvalidToken(NotAuthenticated):
    detail = "Invalid or expired token."


class PermissionDenied(RcAllocationException):
    status_code = 403
    detail = "You do not have permission to perform this action."


class NotFound(RcAllocationException):
    status_code = 404
    detail = "Not found."


class MethodNotAllowed(RcAllocationException):
    status_code = 405

    def __init__(self, method):
        super().__init__(f'Method "{method}" not allowed.')


class Conflict(RcAllocationException):
    status_code = 409
