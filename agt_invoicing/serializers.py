"""
Serializers for AGT Invoicing REST API responses.
All Decimal values serialized as strings to avoid float precision issues.
"""
from decimal import Decimal
from rest_framework import serializers
from .models import Fatura


class FaturaListSerializer(serializers.ModelSerializer):
    """Fatura list serializer (paginated response)."""
    
    total = serializers.SerializerMethodField()
    criada_em = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S')
    
    class Meta:
        model = Fatura
        fields = ['id', 'numero', 'cliente_designacao', 'total', 'agt_status', 'criada_em']
    
    def get_total(self, obj):
        """Return total as string, never float."""
        if obj.total:
            return str(obj.total)
        return "0.00"


class FaturaDetailSerializer(serializers.ModelSerializer):
    """Fatura detail serializer with full fields."""
    
    total = serializers.SerializerMethodField()
    agt_erros = serializers.SerializerMethodField()
    agt_processada_em = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S', allow_null=True)
    
    class Meta:
        model = Fatura
        fields = [
            'numero', 'serie', 'estado', 'total', 'agt_status',
            'agt_request_id', 'agt_hash_validacao', 'agt_erros', 'agt_processada_em'
        ]
    
    def get_total(self, obj):
        """Return total as string, never float."""
        if obj.total:
            return str(obj.total)
        return "0.00"
    
    def get_agt_erros(self, obj):
        """Return agt_erros as JSON object or empty list."""
        if obj.agt_erros:
            return obj.agt_erros
        return []


def serialize_stats(stats_data: dict) -> dict:
    """
    Serialize stats response with Decimal values as strings.
    Args:
        stats_data: dict with counts and groupings
    Returns:
        JSON-serializable dict
    """
    return {
        "emitidas": stats_data.get("emitidas", 0),
        "rejeitadas": stats_data.get("rejeitadas", 0),
        "pendentes": stats_data.get("pendentes", 0),
        "por_estado": stats_data.get("por_estado", {}),
        "por_agt_status": stats_data.get("por_agt_status", {}),
    }
