import logging
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)


def generate_frontmatter(article_id_list, server='ojs', port='80'):
    """
    Generate frontmatter page for articles in OJS via Frontmatter-Plugin.

    Does a simple GET request to the OJS plugin passing on IDs of documents
    already present in OJSself.

    Authorization is done with a specific test user.

    :param article_id_list: IDs of documents in OJS
    :param server: address of the OJS server
    :param port: network port of the OJS server
    :return: tuple containing the response code and text
    """
    ids = ','.join(map(str, article_id_list))
    headers = {'ojsAuthorization': 'YWRtaW4=:cGFzc3dvcmQ='}

    url_base = "/ojs/plugins/generic/ojs-cilantro-plugin/api/frontmatters/"\
               "create/article/"
    url = "http://" + server + ":" + port + url_base + "?id=" + ids

    request = Request(url, headers=headers)

    with urlopen(request) as response:
        response_text = response.read().decode('utf-8')

    return response.getcode(), response_text
