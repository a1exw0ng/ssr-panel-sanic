import random
import time
import re
import ujson
from sanic import Blueprint
from sanic.response import json
from python_paginate.web.sanic_paginate import Pagination
from utils import tools
from utils.decorators import login_required
from ssr_panel.exceptions import BadRequest
from ssr_panel import render
from ssr_panel.models import User, SS_Node, User_Traffic_Log, SS_Checkin_Log, \
    METHOD_CHOICES, PROTOCOL_CHOICES, OBFS_CHOICES

user_panel = Blueprint('user_panel', url_prefix='/dashboard')


@user_panel.route('/')
@login_required
async def index(request):
    user = request['user']
    return render('user_panel/index.html', request, user=user, checkin_time=request.app.config.CHECKIN_TIME)


@user_panel.route('/nodes')
@login_required
async def nodes(request):
    user = request['user']
    nodes = await SS_Node.objects.execute(
        SS_Node
            .select()
            .where((SS_Node.node_group == user.node_group) | (SS_Node.node_group == 0))
    )
    return render('user_panel/nodes.html', request, user=user, nodes=nodes)


@user_panel.route('/nodes/<node_id:int>')
@login_required
async def node_detail(request, node_id):
    user = request['user']
    node = await SS_Node.objects.get(SS_Node.id == node_id)

    if user.user_class < node.node_class or (user.node_group != node.node_group and node.node_group != 0):
        return json({})

    ss_info = {
        'server': node.server,
        'server_port': user.port,
        'password': user.passwd,
        'method': user.method,
        'protocol': user.protocol,
        'obfs': user.obfs
    }
    if user.obfs in ('http_post', 'http_simple'):
        ss_info['obfs_param'] = user.obfs_param

    if user.obfs in ('http_simple', 'http_post', 'random_head', 'tls1.2_ticket_auth') \
            or user.protocol in ('verify_deflate', 'auth_chain_a', 'auth_sha1_v4',
                                 'auth_aes128_md5', 'auth_aes128_sha1'):

        ss_url = '%s:%s:%s:%s:%s:%s/?obfsparam=%s&remarks=%s' % (
            ss_info['server'],
            ss_info['server_port'],
            user.protocol.replace('_compatible', ''),
            ss_info['method'],
            user.obfs.replace('_compatible', ''),
            tools.base64_url_encode(ss_info['password']),
            tools.base64_url_encode(user.obfs_param),
            tools.base64_url_encode(node.name)
        )
        ssqr_s_n = 'ssr://' + tools.base64_url_encode(ss_url)
        ss_url = '%s:%s:%s:%s@%s:%s/%s' % (
            user.obfs.replace('_compatible', ''),
            user.protocol.replace('_compatible', ''),
            ss_info['method'],
            ss_info['password'],
            ss_info['server'],
            ss_info['server_port'],
            tools.base64_encode(user.obfs_param)
        )
        ssqr_s = "ss://" + tools.base64_encode(ss_url)
        ssqr = ssqr_s
    else:
        ss_url = '%s:%s:%s:%s:%s:%s/?obfsparam=%s&remarks=%s' % (
            ss_info['server'],
            ss_info['server_port'],
            user.protocol.replace('_compatible', ''),
            ss_info['method'],
            user.obfs.replace('_compatible', ''),
            tools.base64_url_encode(ss_info['password']),
            tools.base64_url_encode(user.obfs_param or ''),
            tools.base64_url_encode(node.name)
        )
        ssqr_s_n = "ssr://" + tools.base64_encode(ss_url)
        ss_url = '%s:%s:%s:%s@%s:%s/%s' % (
            user.obfs.replace('_compatible', ''),
            user.protocol.replace('_compatible', ''),
            ss_info['method'],
            ss_info['password'],
            ss_info['server'],
            ss_info['server_port'],
            tools.base64_encode(user.obfs_param or '')
        )
        ssqr_s = "ss://" + tools.base64_encode(ss_url)
        ss_url = '%s:%s@%s:%s' % (
            ss_info['method'],
            ss_info['password'],
            ss_info['server'],
            ss_info['server_port']
        )
        ssqr = "ss://" + tools.base64_encode(ss_url)

    surge_base = '/'.join(request.url.split('/')[:3]) + '/downloads/ProxyBase.conf'
    surge_proxy = '#!PROXY-OVERRIDE:ProxyBase.conf\n'
    surge_proxy += '[Proxy]\n'
    surge_proxy += 'Proxy = custom,%s,%s,%s,%s,%s/downloads/SSEncrypt.module' % (
        ss_info['server'],
        ss_info['server_port'],
        ss_info['method'],
        ss_info['password'],
        '/'.join(request.url.split('/')[:3])
    )

    data = {
        'ss_info': ss_info,
        'ss_info_show': ujson.dumps(ss_info, indent=4),
        'ssqr': ssqr,
        'ssqr_s_n': ssqr_s_n,
        'ssqr_s': ssqr_s,
        'surge_base': surge_base,
        'surge_proxy': surge_proxy
    }
    return render('user_panel/node_detail.html', request, user=user, **data)


@user_panel.route('/profile')
@login_required
async def profile(request):
    user = request['user']
    return render('user_panel/profile.html', request, user=user)


@user_panel.route('/trafficlog')
@login_required
async def traffic_log(request):
    user = request['user']

    total = await User_Traffic_Log.objects.count(
        User_Traffic_Log
            .select()
            .where(User_Traffic_Log.user == user)
    )

    page, per_page, offset = Pagination.get_page_args(request)

    traffic_logs = await User_Traffic_Log.objects.execute(
        User_Traffic_Log
            .select()
            .where(User_Traffic_Log.user == user)
            .order_by(User_Traffic_Log.id.desc())
            .paginate(page, per_page)
    )
    ids = [log.id for log in traffic_logs]

    logs_query = (
        User_Traffic_Log
            .select()
            .where(User_Traffic_Log.id << ids)
            .order_by(User_Traffic_Log.id.desc())
    )

    nodes_query = SS_Node.select()

    traffic_logs = await User_Traffic_Log.objects.prefetch(logs_query, nodes_query)

    Pagination._per_page = 20
    pagination = Pagination(request, total=total, record_name='traffic_logs')
    return render('user_panel/traffic_log.html', request, user=user, traffic_logs=traffic_logs,
                  pagination=pagination)


@user_panel.route('/edit')
@login_required
async def edit(request):
    user = request['user']
    return render('user_panel/edit.html', request, user=user)


@user_panel.route('/invite')
@login_required
async def invite(request):
    user = request['user']
    return render('user_panel/invite.html', request, user=user)


@user_panel.route('/checkin', methods=['POST'])
@login_required
async def checkin(request):
    user = request['user']

    if not user.is_able_to_checkin:
        raise BadRequest('您似乎已经签到过了...')

    traffic = random.randint(request.app.config.CHECKIN_MIN, request.app.config.CHECKIN_MAX)
    traffic_to_add = tools.mb_to_byte(traffic)

    res = {'msg': '签到失败，请稍候再试.'}
    async with User.objects.atomic():
        user.transfer_enable += traffic_to_add
        user.last_check_in_time = time.time()
        await User.objects.update(user)

        await SS_Checkin_Log.objects.create(SS_Checkin_Log, user=user, traffic=traffic_to_add)

        res['msg'] = '获得了 %s MB流量.' % traffic

    return json(res)


@user_panel.route('/ssr_edit', methods=['POST'])
@login_required
async def ssr_edit(request):
    sspwd = request.form.get('sspwd', '')
    method = request.form.get('method', '')
    protocol = request.form.get('protocol', '')
    obfs = request.form.get('obfs', '')

    if not re.match('^[\w\-\.@#$]{6,16}$', sspwd):
        raise BadRequest('SS连接密码不符合规则，只能为6-16位长度，包含数字大小写字母-._@#$')

    if method not in dict(METHOD_CHOICES):
        raise BadRequest('加密方法错误')

    if protocol not in dict(PROTOCOL_CHOICES):
        raise BadRequest('协议错误')

    if obfs not in dict(OBFS_CHOICES):
        raise BadRequest('混淆错误')

    user = request['user']
    user.passwd = sspwd
    user.method = method
    user.protocol = protocol
    user.obfs = obfs
    await User.objects.update(user)

    return json({})
