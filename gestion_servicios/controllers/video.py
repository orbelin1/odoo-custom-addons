from odoo import http
from odoo.http import request
from werkzeug.wrappers import Response


class ServicioInspeccionVideoController(http.Controller):

    @http.route(
        "/gestion_servicios/video/<int:attachment_id>",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def stream_video(self, attachment_id):
        attachment = request.env["ir.attachment"].browse(attachment_id).exists()
        if not attachment or not attachment.mimetype.startswith("video/"):
            return request.not_found()
        content = bytes(attachment.raw or b"")
        return Response(
            content,
            headers=[
                ("Content-Type", attachment.mimetype),
                ("Content-Disposition", "inline"),
                ("Accept-Ranges", "bytes"),
            ],
        )
