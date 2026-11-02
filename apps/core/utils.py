def get_client_ip(request) -> str:
    """
    Obtiene la dirección IP real del cliente considerando cabeceras de proxy inverso
    (como Render, Cloudflare, Nginx: HTTP_X_FORWARDED_FOR, HTTP_CF_CONNECTING_IP).
    """
    if not request:
        return '127.0.0.1'

    cf_ip = request.META.get('HTTP_CF_CONNECTING_IP')
    if cf_ip:
        return cf_ip.strip()

    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # El primer elemento de la lista separada por comas es la IP del cliente real
        return x_forwarded_for.split(',')[0].strip()

    return request.META.get('REMOTE_ADDR') or '127.0.0.1'

