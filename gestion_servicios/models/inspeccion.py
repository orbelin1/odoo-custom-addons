import base64
import os

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.binary import BinaryBytes
from odoo.tools.image import image_process
from odoo.tools.mimetypes import guess_mimetype


SECTION_SELECTION = [
    ("detail", "1. Detalle del servicio"),
    ("system_type", "2. Tipo de sistemas"),
    (
        "alarm_inspection",
        "3. Inspección a sistemas de alarmas y detección de incendios",
    ),
    (
        "fire_protection",
        "4. Inspección de asistencia de protección contra incendios",
    ),
    (
        "kitchen_suppression",
        "5. Inspección a sistemas de supresión de incendios de cocina (ANSUL)",
    ),
    ("general_observations", "6. Observaciones generales de servicio"),
    ("conclusion", "7. Conclusión y recomendaciones del servicio"),
    ("equipment_status", "8. Equipo o sistema quedan en"),
    ("training", "9. Capacitación"),
    ("customer_evaluation", "10. Evaluación por parte del cliente"),
    ("received_by", "11. Recibido por"),
]

SECTION_ORDER = [key for key, _label in SECTION_SELECTION]

# Grupos (barras desplegables) de la sección 3
SUBSECTION_SELECTION = [
    ("panel", "Panel de alarmas"),
    ("power", "Fuente de poder auxiliar"),
    ("smoke", "Detectores de humo"),
    ("gas", "Detectores de gas"),
    ("manual", "Estaciones manuales"),
    ("module", "Módulos"),
    ("audiovisual", "Alarmas audiovisuales"),
    # Sección 4
    ("riser", "Tubería vertical (Risers)"),
    ("sprinkler", "Rociadores"),
    ("hydrant", "Red de hidrantes"),
    ("water", "Alimentación de agua"),
    ("diesel", "Bomba diésel"),
    ("electric", "Bomba eléctrica"),
    ("jockey", "Bomba jockey"),
    ("pumproom", "Cuarto de bombas"),
]

# Prefijo de la pregunta (texto antes de los dos puntos) -> grupo
SUBSECTION_PREFIXES = {
    "Panel de alarmas": "panel",
    "Fuente de poder auxiliar": "power",
    "Detectores de humo": "smoke",
    "Detectores de gas": "gas",
    "Detectores de dióxido de carbono": "gas",
    "Estaciones manuales": "manual",
    "Módulos": "module",
    "Módulos relay": "module",
    "Alarmas audiovisuales": "audiovisual",
    # Sección 4
    "Tubería vertical (Risers)": "riser",
    "Rociadores": "sprinkler",
    "Red de hidrantes": "hydrant",
    "Alimentación de agua": "water",
    "Bomba diésel": "diesel",
    "Bomba eléctrica": "electric",
    "Bomba jockey": "jockey",
    "Cuarto de bombas": "pumproom",
}

# Cada pregunta de las secciones 3, 4 y 5 lleva zonas "Fotos ANTES" y
# "Fotos DESPUÉS" con un máximo de PHOTO_LIMIT fotos en cada zona.
PHOTO_LIMIT = 4

# Preguntas que además admiten video (máximo de videos por zona)
VIDEO_RULES = {
    "¿El panel de alarmas se encuentra sin problemas o alarmas activas? (Tomar video de todas las fallas mencionando la falla, el código y la acción correctiva sugerida, en caso de aplicar.)": 1,
    "Indique el resultado de las pruebas de arranque y problema a la bomba jockey.": 1,
}

ALARM_GROUPS = [
    ("Panel de alarmas", [
        "¿El panel de alarmas está encendido y operando?",
        "Indique la cantidad de paneles y ubicación de cada uno.",
        "Indique la(s) marca(s) y modelo(s) del panel de alarmas.",
        "¿El panel de alarmas se encuentra sin problemas o alarmas activas? (Tomar video de todas las fallas mencionando la falla, el código y la acción correctiva sugerida, en caso de aplicar.)",
        "¿La integridad del gabinete del panel de alarmas es óptima?",
        "¿Funcionan correctamente los indicadores LED?",
        "¿Funcionan correctamente el display y teclado?",
        "¿Los voltajes de corriente directa del panel de control son correctos? Indique el valor de los voltajes.",
        "¿La alimentación eléctrica de 120 VCA es regulada, cuenta con 3 hilos (fase, neutro y tierra física), y dispone de un circuito dedicado e identificado?",
        "¿La conexión de terminales, lazos y fuente de poder del panel de control está completa y funciona correctamente?",
        "¿El estado de las baterías del panel es adecuado?",
        "¿Se cuenta con etiqueta de cambio o instalación de baterías de respaldo en el panel de control?",
        "Observaciones",
    ]),
    ("Fuente de poder auxiliar", [
        "Indique la cantidad y ubicación de fuentes de poder de alimentación externa.",
        "¿El estado físico de la fuente de poder auxiliar es óptimo?",
        "Indique el tipo de daño, si aplica.",
        "¿El estado de las baterías en fuente de poder auxiliar es óptimo?",
        "¿El voltaje de NAC de fuente de poder auxiliar es óptimo?",
        "¿Se cuenta con etiqueta de cambio o instalación de baterías de respaldo en fuente de poder auxiliar?",
        "Observaciones",
    ]),
    ("Detectores de humo", [
        "¿Todos los detectores de humo o de temperatura direccionables reportan correctamente al panel?",
        "¿El estado físico de detectores de humo y temperatura es óptimo?",
        "¿Se realizaron pruebas con humo artificial a detectores de humo?",
        "¿Existen detectores autónomos de CA y baterías? Indique cantidad.",
        "Indique otras áreas si no están solamente en habitaciones.",
        "Observaciones",
    ]),
    (None, [  # Detectores de gas y de dióxido de carbono
        "Detectores de gas: ¿la instalación cuenta con detectores direccionados?",
        "Detectores de gas: indique su estado.",
        "Detectores de dióxido de carbono: ¿la instalación cuenta con detectores direccionados?",
        "Detectores de dióxido de carbono: indique su estado.",
        "Detectores de gas: resultados de pruebas con gas patrón, si aplica.",
        "Detectores de gas: observaciones",
    ]),
    ("Estaciones manuales", [
        "¿El estado de las estaciones manuales es óptimo?",
        "¿Se realizó prueba de activación de estaciones manuales?",
        "Observaciones",
    ]),
    (None, [  # Módulos y módulos relay
        "Módulos: indique el estado de los módulos de control.",
        "Módulos: indique el estado de los módulos de supervisión.",
        "Módulos: indique si existen módulos relay y dónde están instalados.",
        "Módulos relay: indique el resultado de la prueba, si aplica.",
    ]),
    ("Alarmas audiovisuales", [
        "¿El estado físico de alarmas audiovisuales es óptimo?",
        "¿La instalación de alarmas audiovisuales es correcta?",
        "¿Existe alarma en la habitación de personas con discapacidad?",
        "¿Se realizaron pruebas de activación?",
        "Observaciones",
    ]),
]

FIRE_GROUPS = [
    ("Tubería vertical (Risers)", [
        "¿La tubería se encuentra libre de corrosión visible, picaduras o desgaste?",
        "¿La tubería está libre de fugas, humedad o rastros de filtración?",
        "¿Los soportes y abrazaderas están firmes y en buen estado?",
        "¿Las válvulas del riser están identificadas correctamente?",
        "¿Las válvulas operan suavemente (abren y cierran completamente sin dificultad)?",
        "¿Las válvulas de control se encuentran supervisadas y/o aseguradas?",
        "¿El sistema mantiene presión adecuada, indique la presión?",
        "Observaciones",
    ]),
    ("Rociadores", [
        "¿Los rociadores se encuentran en buen estado físico (sin corrosión, golpes, pintura o daño visible)?",
        "¿Los rociadores están libres de obstrucciones que puedan afectar la descarga de agua?",
        "¿Los rociadores se encuentran correctamente instalados y alineados?",
        "¿Los rociadores están libres de fugas, humedad o daño en las conexiones?",
        "Observaciones",
    ]),
    ("Red de hidrantes", [
        "Indique la cantidad de hidrantes. Compartir foto de evidencia con número de hidrantes ya con tarjeta de inspección nueva.",
        "¿El estado de las mangueras de hidrantes es correcto?",
        "¿Válvulas angulares se encuentran en buen estado y sin fuga?",
        "La accesibilidad al hidrante no presenta obstrucciones.",
        "¿Están completos los accesorios de hidrante (chiflón, llave spanner, manguera, señalamiento)? Si falta algún accesorio o se encuentra en mal estado indique su ubicación, qué le falta, o cuál es el daño que tiene.",
        "¿El estado de gabinetes (acrílico, soporte, pintura, bisagras y cerradura) es óptimo?",
        "¿La presión y condiciones de operación son correctas?",
        "¿Cuenta con toma siamesa? Favor de compartir fotos.",
        "Observaciones",
    ]),
    ("Alimentación de agua", [
        "¿Se encuentra en funcionamiento la alimentación de agua del sistema?",
        "¿Se cuenta con la capacidad necesaria para el edificio? (85 mt3 mínimo)",
        "Indique el nivel de agua en la cisterna.",
        "Observaciones",
    ]),
    ("Bomba diésel", [
        "¿Se cuenta con bomba de combustión? Enviar foto de la placa.",
        "¿La bomba de combustión está siendo monitoreada por el panel de alarmas?",
        "¿El equipo se encuentra en automático?",
        "¿La temperatura del motor diésel es adecuada, antes del arranque? Indique temperatura.",
        "¿El sistema de enfriamiento del motor diésel es funcional?",
        "¿La línea de inyección y retorno de combustible se encuentra en buenas condiciones y asegurada?",
        "¿El nivel de combustible en el tanque diésel es el adecuado, mínimo 3/4?",
        "¿Las baterías del motor diésel son funcionales? Validar con probador de baterías.",
        "Indique fecha del último cambio de baterías.",
        "¿El By-Pass del sistema de enfriamiento del motor diésel está cerrado?",
        "¿Se encuentran las válvulas del sistema de enfriamiento en su posición correcta?",
        "¿Tubería de escape se encuentra en buenas condiciones?",
        "¿Tablero de instrumentos opera correctamente?",
        "¿Los niveles de aditivos (aceite, anticongelante, y líquido en baterías) son correctos?",
        "¿El precalentador del motor diésel está funcionando?",
        "¿Al realizarse la limpieza del equipo se detectaron fugas? Indique la ubicación de las fugas encontradas.",
        "¿Realizó los 6 intentos de arranque indicados por NFPA? (de forma anual)",
        "Indique el resultado de la prueba al tablero del motor (de forma anual).",
        "¿Cuenta el equipo con línea de pruebas Venturi?",
        "Indique si se realizó la prueba de eficiencia a la bomba (de forma anual).",
        "Indique el resultado de las pruebas de arranque de la bomba diésel.",
    ]),
    ("Bomba eléctrica", [
        "¿Se cuenta con bomba eléctrica principal? Enviar foto de la placa.",
        "¿El estado de la bomba eléctrica es óptimo?",
        "¿La bomba eléctrica está monitoreada desde el panel de alarmas?",
        "¿El controlador de la bomba eléctrica está funcionando?",
        "Indique el dato de GPM de la bomba. Validar en la placa de la bomba.",
        "Indique el dato de PSI de la bomba. Validar en la placa de la bomba.",
        "Indique el dato de HP de la bomba. Validar en la placa de la bomba.",
        "¿La bomba eléctrica de incendios está en automático?",
        "Indique el estado del motor eléctrico.",
        "Indique si el enfriamiento del motor es el adecuado. (En caso de aceite indique el nivel)",
        "¿Cuenta con válvula de alivio a la descarga de la bomba?",
        "Indique el resultado de las pruebas de arranque y problema a la bomba eléctrica.",
    ]),
    ("Bomba jockey", [
        "¿Se cuenta con bomba jockey? Enviar foto de la placa.",
        "¿El estado de la bomba jockey es óptimo?",
        "¿El controlador de la bomba jockey está funcionando?",
        "¿La bomba jockey está en automático?",
        "Indique los hallazgos al realizar la limpieza de bomba jockey y su controlador.",
        "Indique el funcionamiento de bomba jockey en manual y en automático.",
        "Indique el resultado de las pruebas de arranque y problema a la bomba jockey.",
    ]),
    ("Cuarto de bombas", [
        "¿Temperatura y humedad del cuarto de bombas es aceptable para permanecer en el interior?",
        "¿Es adecuada la ventilación del cuarto de bombas?",
        "¿Las válvulas de succión y descarga de las bombas están abiertas, aseguradas o supervisadas?",
        "¿Las condiciones de tuberías de succión, descarga, válvulas y retorno a tanque cisterna o reserva de agua son óptimas?",
        "Observaciones",
    ]),
]

KITCHEN_GROUPS = [
    (None, [
        "¿Cuántos sistemas de supresión de cocina están instalados?",
        "¿Cuántos tanques por sistema están instalados?",
        "¿Cuál es la capacidad de los tanques instalados?",
        "¿El sistema de supresión de incendios en cocina está en operación?",
        "¿Se cuenta con válvulas de corte de gas?",
        "¿El estado de las válvulas de corte de gas es óptimo?",
        "¿Cuál es el diámetro de las válvulas de corte de gas?",
        "¿El estado de los cilindros y sus conexiones son óptimos?",
        "¿El estado de las boquillas de descarga es óptimo y se encuentran alineadas?",
        "¿El estado de las estaciones manuales del sistema de supresión de cocina es óptimo?",
        "¿Cuentan con su testigo las estaciones manuales?",
        "¿Cuentan con sus tapones las boquillas?",
        "¿El estado de la instalación del sistema de supresión de cocina es óptimo?",
        "Verifique el estado del cartucho de nitrógeno, indique peso y fecha de prueba hidrostática.",
        "Verifique el estado del tanque de Ansulex (indique su hermeticidad y sello).",
        "¿Se realizó el cambio de los fusibles?",
        "Indique el resultado de las pruebas de activación sin descarga.",
        "Observaciones",
    ]),
]


def _build_questions(groups):
    """Convierte los grupos en la lista de preguntas."""
    questions = []
    for prefix, items in groups:
        for text in items:
            questions.append("%s: %s" % (prefix, text) if prefix else text)
    return questions


SECTION_QUESTIONS = {
    "detail": [
        "Tipo de reporte",
        "Cliente",
        "Ubicación",
        "Fecha de realización",
        "Nombre del técnico",
        "Nombre de representante del cliente",
        "Número de reporte",
    ],
    "system_type": ["Tipo de sistema"],
    "training": ["¿Se impartió capacitación?"],
    "customer_evaluation": [
        "¿Cómo considera la calidad del servicio?",
        "¿Cómo considera el conocimiento del técnico sobre los sistemas?",
        "¿Cómo considera la comunicación del técnico?",
        "¿Cómo considera la presentación del técnico?",
        "Escriba alguna queja, sugerencia o cómo le pareció el servicio.",
    ],
}

MEDIA_SECTIONS = ("alarm_inspection", "fire_protection", "kitchen_suppression")

for _section, _groups in zip(MEDIA_SECTIONS, (ALARM_GROUPS, FIRE_GROUPS, KITCHEN_GROUPS)):
    SECTION_QUESTIONS[_section] = _build_questions(_groups)


def _media_vals(section, question):
    if section not in MEDIA_SECTIONS:
        return {"media_rule": False, "photo_limit": 0, "video_limit": 0}
    return {
        "media_rule": True,
        "photo_limit": PHOTO_LIMIT,
        "video_limit": VIDEO_RULES.get(question.split(": ", 1)[-1], 0),
    }


# Las 4 primeras preguntas de la sección 10 se responden con calificación
RATING_QUESTIONS = set(SECTION_QUESTIONS["customer_evaluation"][:4])

RATING_SELECTION = [
    ("excellent", "Excelente"),
    ("very_good", "Muy bueno"),
    ("acceptable", "Aceptable"),
    ("regular", "Regular"),
]


class ServicioInspeccion(models.Model):
    _name = "servicio.inspeccion"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "Reporte de inspección de servicios"
    _order = "create_date desc"

    name = fields.Char(
        string="Número de reporte",
        copy=False,
        readonly=True,
        default="Nuevo",
    )
    state = fields.Selection(
        [("draft", "Borrador"), ("in_progress", "En inspección"), ("done", "Finalizado")],
        string="Estado",
        default="draft",
        required=True,
    )
    section = fields.Selection(
        SECTION_SELECTION,
        string="Sección actual",
        default="detail",
        required=True,
    )
    report_type = fields.Char(string="Tipo de reporte", required=True)
    customer_id = fields.Many2one("res.partner", string="Cliente", required=True)
    location = fields.Char(string="Ubicación", required=True)
    inspection_date = fields.Date(string="Fecha de realización", default=fields.Date.context_today)
    technician_id = fields.Many2one(
        "res.users", string="Nombre del técnico", default=lambda self: self.env.user, required=True
    )
    customer_representative = fields.Char(string="Representante del cliente")
    system_type = fields.Selection(
        [("fire", "Sistema contra incendio"), ("alarm", "Sistema de alarmas y detección"), ("kitchen", "Sistema de supresión en cocina")],
        string="Tipo de sistema",
        required=True,
        default="alarm",
    )
    inspection_item_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id", string="Respuestas de inspección", copy=True
    )

    # Un campo por cada barra desplegable de la sección 3
    item_panel_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "panel")], string="Panel de alarmas")
    item_power_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "power")], string="Fuente de poder auxiliar")
    item_smoke_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "smoke")], string="Detectores de humo")
    item_gas_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "gas")], string="Detectores de gas")
    item_manual_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "manual")], string="Estaciones manuales")
    item_module_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "module")], string="Módulos")
    item_audiovisual_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "audiovisual")], string="Alarmas audiovisuales")

    item_riser_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "riser")], string="Tubería vertical (Risers)")
    item_sprinkler_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "sprinkler")], string="Rociadores")
    item_hydrant_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "hydrant")], string="Red de hidrantes")
    item_water_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "water")], string="Alimentación de agua")
    item_diesel_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "diesel")], string="Bomba diésel")
    item_electric_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "electric")], string="Bomba eléctrica")
    item_jockey_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "jockey")], string="Bomba jockey")
    item_pumproom_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("subsection", "=", "pumproom")], string="Cuarto de bombas")

    # Sección 5, 9 y 10 (listas)
    item_kitchen_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("section", "=", "kitchen_suppression")], string="Supresión de cocina")
    item_training_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("section", "=", "training")], string="Capacitación")
    item_evaluation_ids = fields.One2many(
        "servicio.inspeccion.item", "inspection_id",
        domain=[("section", "=", "customer_evaluation")], string="Evaluación del cliente")

    # Sección 6: Observaciones generales de servicio
    observations_text = fields.Text(string="Deficiencias encontradas")
    observations_note = fields.Text(string="Nota")
    observations_attachment_ids = fields.Many2many("ir.attachment", "servicio_insp_obs_att_rel", string="Archivos multimedia")

    # Sección 7: Conclusión y recomendaciones
    recommendations_text = fields.Text(string="Recomendaciones generales")
    recommendations_note = fields.Text(string="Nota")
    recommendations_attachment_ids = fields.Many2many("ir.attachment", "servicio_insp_rec_att_rel", string="Archivos multimedia")

    # Sección 8: Equipo o sistema quedan en
    equipment_status_text = fields.Text(string="Estado en que quedan los equipos")
    equipment_status_note = fields.Text(string="Nota")
    equipment_status_attachment_ids = fields.Many2many("ir.attachment", "servicio_insp_eq_att_rel", string="Archivos multimedia")

    # Sección 11: Recibido por
    report_made_by = fields.Char(
        string="Reporte elaborado por", default=lambda self: self.env.user.name)
    report_made_signature = fields.Binary(
        string="Firma de quien elabora", attachment=True, copy=False)
    report_date = fields.Date(string="Fecha", default=fields.Date.context_today)
    report_received_by = fields.Char(string="Reporte recibido por")
    report_received_signature = fields.Binary(
        string="Firma de quien recibe", attachment=True, copy=False)
    received_note = fields.Text(string="Nota")
    received_attachment_ids = fields.Many2many("ir.attachment", "servicio_insp_recv_att_rel", string="Archivos multimedia")

    notes = fields.Text(string="Observaciones generales")
    attachment_ids = fields.Many2many("ir.attachment", string="Archivos multimedia")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "Nuevo") == "Nuevo":
                vals["name"] = self.env["ir.sequence"].next_by_code("servicio.inspeccion") or "Nuevo"
        records = super().create(vals_list)
        records._ensure_section_items()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "section" in vals:
            self._ensure_section_items()
        return result

    def _ensure_section_items(self):
        line_model = self.env["servicio.inspeccion.item"]
        for record in self:
            existing = set(record.inspection_item_ids.mapped("section"))
            for section, questions in SECTION_QUESTIONS.items():
                if section in existing:
                    continue
                line_model.create([
                    {
                        "inspection_id": record.id,
                        "section": section,
                        "sequence": index,
                        "question": question,
                        "answer_type": "rating" if question in RATING_QUESTIONS else "text",
                        **_media_vals(section, question),
                    }
                    for index, question in enumerate(questions, 1)
                ])

    def _move_section(self, offset):
        for record in self:
            current = SECTION_ORDER.index(record.section)
            target = max(0, min(len(SECTION_ORDER) - 1, current + offset))
            record.section = SECTION_ORDER[target]
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_next_section(self):
        return self._move_section(1)

    def action_previous_section(self):
        return self._move_section(-1)

    def action_start_inspection(self):
        self.write({"state": "in_progress"})
        return True

    def action_complete_inspection(self):
        self.write({"state": "done"})
        return True

    def action_download_report(self):
        self.ensure_one()
        return self.env.ref(
            "gestion_servicios.action_report_inspeccion"
        ).report_action(self)

    def action_send_email(self):
        """Abre el correo al cliente con el PDF del reporte adjunto."""
        self.ensure_one()
        template = self.env.ref("gestion_servicios.mail_template_inspeccion")
        return {
            "type": "ir.actions.act_window",
            "name": "Enviar reporte por correo",
            "res_model": "mail.compose.message",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_model": self._name,
                "default_res_ids": self.ids,
                "default_template_id": template.id,
                "default_composition_mode": "comment",
                "default_email_layout_xmlid": "mail.mail_notification_light",
                "force_email": True,
            },
        }


class ServicioInspeccionItem(models.Model):
    _name = "servicio.inspeccion.item"
    _description = "Respuesta de inspección de servicio"
    _order = "section, sequence, id"

    inspection_id = fields.Many2one("servicio.inspeccion", required=True, ondelete="cascade")
    section = fields.Selection(SECTION_SELECTION, required=True, index=True)
    subsection = fields.Selection(
        SUBSECTION_SELECTION,
        string="Grupo",
        compute="_compute_subsection",
        store=True,
        index=True,
    )
    sequence = fields.Integer(default=10)
    question = fields.Char(string="Pregunta", required=True, readonly=True)
    answer = fields.Text(string="Respuesta")
    answer_type = fields.Selection(
        [("text", "Texto"), ("rating", "Calificación")],
        default="text",
        required=True,
    )
    rating = fields.Selection(RATING_SELECTION, string="Calificación")

    # Fotos / videos por pregunta (zonas ANTES y DESPUÉS)
    media_rule = fields.Boolean(default=False)
    photo_limit = fields.Integer(string="Fotos permitidas", default=0)
    video_limit = fields.Integer(string="Videos permitidos", default=0)
    attachment_before_ids = fields.Many2many(
        "ir.attachment",
        "servicio_insp_item_before_rel",
        "item_id",
        "attachment_id",
        string="Fotos ANTES",
    )
    attachment_after_ids = fields.Many2many(
        "ir.attachment",
        "servicio_insp_item_after_rel",
        "item_id",
        "attachment_id",
        string="Fotos DESPUÉS",
    )
    note = fields.Text(string="Nota")
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "servicio_inspeccion_item_attachment_rel",
        "item_id",
        "attachment_id",
        string="Archivos multimedia",
    )

    @staticmethod
    def _count_media(attachments):
        images = len(attachments.filtered(lambda a: (a.mimetype or "").startswith("image/")))
        videos = len(attachments.filtered(lambda a: (a.mimetype or "").startswith("video/")))
        return images, videos

    @api.constrains("attachment_before_ids", "attachment_after_ids")
    def _check_media_limits(self):
        for item in self:
            if not item.media_rule:
                continue
            for label, atts in (
                ("ANTES", item.attachment_before_ids),
                ("DESPUÉS", item.attachment_after_ids),
            ):
                images, videos = self._count_media(atts)
                if images > item.photo_limit:
                    detail = (
                        "permite como máximo %d foto(s)" % item.photo_limit
                        if item.photo_limit else "no admite fotos, solo video"
                    )
                    raise ValidationError(
                        "En la pregunta «%s», la zona %s %s. Subiste %d."
                        % (item.question_short or item.question, label, detail, images)
                    )
                if videos > item.video_limit:
                    detail = (
                        "permite como máximo %d video(s)" % item.video_limit
                        if item.video_limit else "no admite videos"
                    )
                    raise ValidationError(
                        "En la pregunta «%s», la zona %s %s. Subiste %d."
                        % (item.question_short or item.question, label, detail, videos)
                    )

    question_short = fields.Char(
        string="Pregunta",
        compute="_compute_question_short",
    )

    @api.depends("question", "section")
    def _compute_question_short(self):
        for item in self:
            text = item.question or ""
            if item.section in ("alarm_inspection", "fire_protection") and ":" in text:
                prefix, rest = text.split(":", 1)
                if prefix.strip() in SUBSECTION_PREFIXES:
                    text = rest.strip()
                    text = text[:1].upper() + text[1:]
            item.question_short = text

    @api.depends("question", "section")
    def _compute_subsection(self):
        for item in self:
            prefix = (item.question or "").split(":")[0].strip()
            item.subsection = (
                SUBSECTION_PREFIXES.get(prefix)
                if item.section in ("alarm_inspection", "fire_protection")
                else False
            )



# ======================= REPORTE PDF =======================

def _section_items(doc, section):
    return doc.inspection_item_ids.filtered(
        lambda i: i.section == section
    ).sorted(lambda i: (i.sequence, i.id))


def _grouped_items(doc, section):
    """Devuelve [(titulo_de_la_barra, renglones), ...] de una sección."""
    items = _section_items(doc, section)
    result = []
    for key, label in SUBSECTION_SELECTION:
        group = items.filtered(lambda i, k=key: i.subsection == k)
        if group:
            result.append((label, group))
    known = {key for key, _label in SUBSECTION_SELECTION}
    rest = items.filtered(lambda i: i.subsection not in known)
    if rest:
        result.append(("Otros", rest))
    return result


def _is_image(attachment):
    return (attachment.mimetype or "").startswith("image/")


def _image_uri(attachment):
    """Imagen incrustada y reducida (máx. 1600 px) para que el PDF no pese de más."""
    att = attachment.sudo()
    raw = bytes(att.raw or b"")
    if not raw:
        return ""
    mimetype = att.mimetype or "image/png"
    if mimetype != "image/svg+xml":
        try:
            resized = image_process(raw, size=(1600, 1600), quality=85)
            if resized:
                raw = resized
        except Exception:
            pass
    return "data:%s;base64,%s" % (mimetype, base64.b64encode(raw).decode())


def _signature_uri(value):
    """En Odoo 20 los campos binarios ya traen el contenido (bytes), no base64."""
    if not value:
        return ""
    return "data:image/png;base64," + base64.b64encode(bytes(value)).decode()


class ReportInspeccion(models.AbstractModel):
    _name = "report.gestion_servicios.report_inspeccion_document"
    _description = "Reporte PDF de inspección de servicio"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["servicio.inspeccion"].browse(docids)
        cache = {}

        def image_uri(attachment):
            if attachment.id not in cache:
                cache[attachment.id] = _image_uri(attachment)
            return cache[attachment.id]

        base_url = self.get_base_url().rstrip("/")

        def photo_url(attachment):
            """Enlace a la foto completa; el token permite abrirla sin iniciar sesión."""
            att = attachment.sudo()
            token = att.generate_access_token()[0]
            return "%s/web/image/%s?access_token=%s" % (base_url, att.id, token)

        return {
            "doc_ids": docids,
            "doc_model": "servicio.inspeccion",
            "docs": docs,
            "section_items": _section_items,
            "grouped": _grouped_items,
            "is_image": _is_image,
            "image_uri": image_uri,
            "photo_url": photo_url,
            "signature_uri": _signature_uri,
        }



# ======================= COMPRESIÓN DE FOTOS =======================

IMAGE_TARGET_KB = 100  # tamaño objetivo de cada foto (en KB)
_COMPRESS_MODELS = ("servicio.inspeccion", "servicio.inspeccion.item")
# (lado máximo en px, calidad JPEG): se prueban en orden hasta llegar al objetivo
_COMPRESS_STEPS = (
    (1600, 80), (1280, 72), (1024, 65), (900, 60),
    (800, 55), (640, 50), (512, 45), (400, 40),
)


def _compress_image(raw):
    """Reduce una foto a ~IMAGE_TARGET_KB. Si no se puede, devuelve la original."""
    target = IMAGE_TARGET_KB * 1024
    if len(raw) <= target:
        return raw
    best = None
    for size, quality in _COMPRESS_STEPS:
        try:
            data = image_process(
                raw, size=(size, size), quality=quality, output_format="JPEG"
            )
        except Exception:
            return raw
        if not data:
            return raw
        best = data
        if len(data) <= target:
            break
    return best if best and len(best) < len(raw) else raw


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @staticmethod
    def _compress_vals(vals, raw):
        """Comprime la foto de `raw` y ajusta `vals`. Devuelve False si no aplica."""
        if vals.get("res_model") not in _COMPRESS_MODELS or not raw:
            return False
        raw = bytes(raw)
        mimetype = vals.get("mimetype") or guess_mimetype(raw)
        if mimetype not in ("image/jpeg", "image/png", "image/webp"):
            return False  # videos, PDF, etc. no se tocan
        new_raw = _compress_image(raw)
        if new_raw is raw:
            return False
        vals["raw"] = BinaryBytes(new_raw)
        vals["mimetype"] = "image/jpeg"
        if vals.get("name"):
            vals["name"] = os.path.splitext(vals["name"])[0] + ".jpg"
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            raw = vals.get("raw")
            if raw and not isinstance(raw, str):
                self._compress_vals(vals, raw)
        return super().create(vals_list)

    def _upload_file(self, file, create_vals):
        # Las fotos subidas desde el formulario llegan aquí, no por create()
        vals = dict(create_vals)
        if vals.get("res_model") in _COMPRESS_MODELS and (
            vals.get("mimetype") or ""
        ).startswith("image/"):
            raw = file.read()
            if self._compress_vals(vals, raw):
                return self.create(vals)
            return self.create(dict(create_vals, raw=BinaryBytes(raw)))
        return super()._upload_file(file, create_vals)
