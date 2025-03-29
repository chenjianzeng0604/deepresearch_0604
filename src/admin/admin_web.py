#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
后台管理系统 Web应用
可以在开发工具中直接点击启动运行
"""

import os
import sys
import logging
import hashlib
import pymysql
from pathlib import Path
import asyncio
import threading
import json
import random
from datetime import datetime, timedelta
from functools import wraps

# =============== 路径配置 ===============
# 确保在任何环境下都能正确找到项目根目录
FILE_PATH = Path(__file__).resolve()
ROOT_DIR = FILE_PATH.parent.parent.parent
sys.path.append(str(ROOT_DIR))  # 将项目根目录添加到Python路径

# 确保工作目录是项目根目录
os.chdir(str(ROOT_DIR))

# =============== 编码配置 ===============
# 确保终端显示中文
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# =============== 导入依赖 ===============
try:
    from flask import Flask, render_template, redirect, url_for, flash, request, session, abort, jsonify, make_response, Blueprint
    from dotenv import load_dotenv
except ImportError as e:
    print(f"错误: 缺少必要依赖，请安装: pip install flask python-dotenv pymysql")
    sys.exit(1)

# 导入数据库模块
from src.admin.crawler_config_manager import CrawlerConfigManager

# 加载环境变量
env_path = os.path.join(ROOT_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path)
else:
    print(f"警告: 环境变量文件不存在: {env_path}")

# =============== 日志配置 ===============
from src.utils.log_utils import setup_logging
logger = setup_logging(app_name="admin_web")

# 创建一个变量来存储CrawlerConfigManager实例，但不立即初始化
crawler_config_manager = None

def get_crawler_config_manager():
    """获取或初始化CrawlerConfigManager（带错误处理）"""
    global crawler_config_manager
    if crawler_config_manager is None:
        try:
            crawler_config_manager = CrawlerConfigManager()
        except Exception as e:
            print(f"初始化CrawlerConfigManager出错: {str(e)}")
    return crawler_config_manager

# 使用共享的认证工具
from src.utils.auth_utils import login_required
from src.utils.auth_utils import db_required as create_db_required

# 为特定应用实例化db_required装饰器
db_required = create_db_required(get_crawler_config_manager)

# 辅助函数 - 密码哈希
def hash_password(password):
    """使用SHA-256对密码进行哈希"""
    return hashlib.sha256(password.encode()).hexdigest()

# =============== 应用初始化 ===============
def create_app():
    """创建并配置Flask应用实例"""
    # 创建Flask应用
    app = Flask(__name__, 
                template_folder=os.path.join(ROOT_DIR, 'templates'),
                static_folder=os.path.join(ROOT_DIR, 'static'))
    
    # 设置会话密钥
    app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_secret_key')
    
    # 配置应用程序
    app.config['JSON_AS_ASCII'] = False  # 确保JSON响应能正确处理中文
    app.config['TEMPLATES_AUTO_RELOAD'] = True  # 自动重新加载模板
    
    # 根路由 - 重定向到管理登录页面
    @app.route('/')
    def index():
        """重定向到管理登录页面"""
        return redirect(url_for('login'))
    
    # 错误处理
    @app.errorhandler(404)
    def page_not_found(e):
        """404页面"""
        return render_template('admin/error.html', error="页面不存在", message="找不到请求的页面"), 404
    
    @app.errorhandler(500)
    def server_error(e):
        """500页面"""
        return render_template('admin/error.html', error="服务器内部错误", message="服务器处理请求时发生错误"), 500
    
    # ====================== 管理员登录相关路由 ======================
    
    @app.route('/admin/login', methods=['GET', 'POST'])
    def login():
        """管理员登录"""
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            if not username or not password:
                flash('请输入用户名和密码', 'danger')
                return render_template('admin/login.html')
                
            manager = get_crawler_config_manager()
            if not manager:
                flash('数据库连接不可用，请联系系统管理员', 'danger')
                return render_template('admin/login.html')
            
            user = manager.verify_admin_login(username, password)
            if user:
                # 登录成功，设置会话
                session['admin_logged_in'] = True
                session['admin_id'] = user['id']
                session['admin_username'] = user['username']
                
                flash(f'欢迎回来，{user["username"]}!', 'success')
                
                # 重定向到之前尝试访问的页面，或默认到管理首页
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/admin'):
                    return redirect(next_page)
                return redirect(url_for('dashboard'))
            else:
                flash('用户名或密码错误', 'danger')
                
        return render_template('admin/login.html')
    
    @app.route('/admin/register', methods=['GET', 'POST'])
    def register():
        """管理员注册"""
        # 检查是否已有管理员账户
        manager = get_crawler_config_manager()
        if not manager:
            flash('数据库连接不可用，请联系系统管理员', 'danger')
            return render_template('admin/register.html')
            
        try:
            # 检查是否已存在管理员账户
            with manager.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM crawler_admin_users")
                admin_count = cursor.fetchone()['count']
                
                # 如果已有管理员，则重定向到登录页面
                if admin_count > 0 and 'admin_logged_in' not in session:
                    flash('已有管理员账户，请登录', 'warning')
                    return redirect(url_for('login'))
        except Exception as e:
            logger.error(f"查询管理员账户失败: {str(e)}")
            flash('数据库查询失败，请联系系统管理员', 'danger')
            return render_template('admin/register.html')
            
        # 处理注册表单
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            confirm_password = request.form.get('confirm_password')
            email = request.form.get('email', '')
            
            # 基本验证
            if not username or not password:
                flash('请输入用户名和密码', 'danger')
                return render_template('admin/register.html')
                
            if password != confirm_password:
                flash('两次输入的密码不一致', 'danger')
                return render_template('admin/register.html')
            
            # 注册新管理员
            user_id = manager.register_admin(username, password, email)
            if user_id:
                flash('注册成功，请登录', 'success')
                return redirect(url_for('login'))
            else:
                flash('注册失败，请稍后再试', 'danger')
                
        return render_template('admin/register.html')
    
    @app.route('/admin/logout')
    def logout():
        """管理员登出"""
        session.pop('admin_logged_in', None)
        session.pop('admin_id', None)
        session.pop('admin_username', None)
        flash('您已成功退出登录', 'success')
        return redirect(url_for('login'))
    
    # ====================== 管理后台路由 ======================
    
    @app.route('/admin/dashboard')
    @login_required
    @db_required
    def dashboard():
        """管理后台首页"""
        manager = get_crawler_config_manager()
        
        # 获取统计数据
        stats = {
            'scenarios': 0,
            'platforms': 0,
            'url_formats': 0,
            'direct_urls': 0,
            'scheduled_tasks': 0
        }
        
        try:
            with manager.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM crawler_scenarios")
                stats['scenarios'] = cursor.fetchone()['count']
                
                cursor.execute("SELECT COUNT(*) as count FROM crawler_platforms")
                stats['platforms'] = cursor.fetchone()['count']
                
                cursor.execute("SELECT COUNT(*) as count FROM crawler_url_formats")
                stats['url_formats'] = cursor.fetchone()['count']
                
                cursor.execute("SELECT COUNT(*) as count FROM crawler_direct_urls")
                stats['direct_urls'] = cursor.fetchone()['count']
                
                cursor.execute("SELECT COUNT(*) as count FROM crawler_scheduled_tasks")
                stats['scheduled_tasks'] = cursor.fetchone()['count']
        except Exception as e:
            logger.error(f"获取统计数据失败: {str(e)}")
            flash('获取统计数据失败', 'danger')
            
        return render_template('admin/dashboard.html', stats=stats)
    
    # 场景管理路由
    @app.route('/admin/scenarios')
    @login_required
    @db_required
    def admin_scenarios():
        # Get all scenarios with counts
        manager = get_crawler_config_manager()
        try:
            scenarios = manager.get_all_scenarios_with_counts()
        except Exception as e:
            flash(f'加载场景数据时出错: {str(e)}', 'danger')
            scenarios = []
        
        return render_template('scenarios.html', active_page='scenarios', scenarios=scenarios)


    @app.route('/admin/scenarios/add', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_add_scenario():
        errors = {}
        form_data = {}
        
        if request.method == 'POST':
            # 获取表单数据
            name = request.form.get('name', '').strip()
            display_name = request.form.get('display_name', '').strip()
            description = request.form.get('description', '').strip()
            collection_name = request.form.get('collection_name', '').strip()
            is_default = True if request.form.get('is_default') else False
            
            # 保存表单数据用于错误后重新填充
            form_data = {
                'name': name,
                'display_name': display_name,
                'description': description,
                'collection_name': collection_name,
                'is_default': is_default
            }
            
            # 验证数据
            if not name:
                errors['name'] = '场景名称不能为空'
            elif not name.isascii() or not all(c.islower() or c.isdigit() or c == '_' for c in name):
                errors['name'] = '场景名称只能包含小写字母、数字和下划线'
                
            if not display_name:
                errors['display_name'] = '显示名称不能为空'
                
            if not collection_name:
                errors['collection_name'] = 'Milvus集合名称不能为空'
            elif not collection_name.isascii() or not all(c.isupper() or c.isdigit() or c == '_' for c in collection_name):
                errors['collection_name'] = 'Milvus集合名称只能包含大写字母、数字和下划线'
            
            # 如果没有错误，则保存场景
            if not errors:
                try:
                    # 检查场景名称是否已存在
                    manager = get_crawler_config_manager()
                    existing_scenario = manager.get_scenario_by_name(name)
                    
                    if existing_scenario:
                        errors['name'] = f'场景名称 "{name}" 已存在，请使用其他名称'
                    else:
                        # 添加场景到数据库
                        scenario_id = manager.add_scenario(
                            name=name,
                            display_name=display_name,
                            description=description,
                            collection_name=collection_name,
                            is_default=is_default
                        )
                        
                        if scenario_id:
                            # 如果设置为默认场景，记录日志
                            if is_default:
                                manager.set_default_scenario(scenario_id)
                                flash(f'成功添加场景：{display_name}，并设为默认场景', 'success')
                            else:
                                flash(f'成功添加场景：{display_name}', 'success')
                            
                            # 添加成功后，引导用户添加URL格式
                            return redirect(url_for('admin_scenarios'))
                        else:
                            flash('添加场景失败，请稍后再试', 'danger')
                except Exception as e:
                    flash(f'添加场景时出错：{str(e)}', 'danger')
        
        # 传递错误和表单数据到模板
        return render_template('scenario_form.html', 
                               active_page='scenarios', 
                               title='添加爬虫场景',
                               errors=errors,
                               form_data=form_data)


    @app.route('/admin/scenarios/edit/<int:scenario_id>', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_edit_scenario(scenario_id):
        # 获取场景数据
        manager = get_crawler_config_manager()
        scenario = manager.get_scenario_by_id(scenario_id)
        
        if not scenario:
            flash('找不到指定的场景', 'danger')
            return redirect(url_for('admin_scenarios'))
        
        errors = {}
        form_data = {}
        
        if request.method == 'POST':
            # 获取表单数据
            display_name = request.form.get('display_name', '').strip()
            description = request.form.get('description', '').strip()
            collection_name = request.form.get('collection_name', '').strip()
            is_default = True if request.form.get('is_default') else False
            is_active = True if request.form.get('is_active') else False
            
            # 保存表单数据用于错误后重新填充
            form_data = {
                'display_name': display_name,
                'description': description,
                'collection_name': collection_name,
                'is_default': is_default,
                'is_active': is_active
            }
            
            # 验证数据
            if not display_name:
                errors['display_name'] = '显示名称不能为空'
                
            if not collection_name:
                errors['collection_name'] = 'Milvus集合名称不能为空'
            elif not collection_name.isascii() or not all(c.isupper() or c.isdigit() or c == '_' for c in collection_name):
                errors['collection_name'] = 'Milvus集合名称只能包含大写字母、数字和下划线'
            
            # 如果没有错误，则更新场景
            if not errors:
                try:
                    # 更新场景到数据库
                    success = manager.update_scenario(
                        scenario_id=scenario_id,
                        display_name=display_name,
                        description=description,
                        collection_name=collection_name,
                        is_default=is_default,
                        is_active=is_active
                    )
                    
                    if success:
                        flash(f'成功更新场景：{display_name}', 'success')
                        return redirect(url_for('admin_scenarios'))
                    else:
                        flash('更新场景失败，请稍后再试', 'danger')
                except Exception as e:
                    flash(f'更新场景时出错：{str(e)}', 'danger')
        else:
            # GET请求，填充表单数据
            form_data = {
                'display_name': scenario['display_name'],
                'description': scenario['description'],
                'collection_name': scenario['collection_name'],
                'is_default': scenario['is_default'],
                'is_active': scenario['is_active']
            }
        
        # 传递错误和表单数据到模板
        return render_template('scenario_form.html', 
                               active_page='scenarios', 
                               title='编辑爬虫场景',
                               edit_mode=True,
                               scenario=scenario,
                               errors=errors,
                               form_data=form_data)


    @app.route('/admin/scenarios/delete/<int:scenario_id>', methods=['POST'])
    @login_required
    @db_required
    def admin_delete_scenario(scenario_id):
        # Get scenario data
        manager = get_crawler_config_manager()
        scenario = manager.get_scenario_by_id(scenario_id)
        
        if not scenario:
            flash('找不到指定的场景', 'danger')
            return redirect(url_for('admin_scenarios'))
        
        # Check if it's the default scenario
        if scenario.get('is_default'):
            flash('不能删除默认场景', 'danger')
            return redirect(url_for('admin_scenarios'))
        
        try:
            # Delete scenario from database
            result = manager.delete_scenario(scenario_id)
            
            if result:
                flash(f'成功删除场景：{scenario["display_name"]}', 'success')
            else:
                flash('删除场景失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'删除场景时出错：{str(e)}', 'danger')
        
        return redirect(url_for('admin_scenarios'))


    @app.route('/admin/scenarios/set-default/<int:scenario_id>', methods=['POST'])
    @login_required
    @db_required
    def admin_set_default_scenario(scenario_id):
        """设置默认场景"""
        manager = get_crawler_config_manager()
        
        # 检查场景是否存在
        scenario = manager.get_scenario_by_id(scenario_id)
        if not scenario:
            flash('找不到指定的场景', 'danger')
            return redirect(url_for('admin_scenarios'))
        
        # 设置为默认场景
        try:
            if manager.set_default_scenario(scenario_id):
                flash(f'已将 {scenario["display_name"]} 设为默认场景', 'success')
            else:
                flash('设置默认场景失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'设置默认场景时出错：{str(e)}', 'danger')
        
        return redirect(url_for('admin_scenarios'))


    @app.route('/admin/scenarios/toggle/<int:scenario_id>', methods=['POST'])
    @login_required
    @db_required
    def admin_toggle_scenario(scenario_id):
        """启用或禁用场景"""
        manager = get_crawler_config_manager()
        
        # 检查场景是否存在
        scenario = manager.get_scenario_by_id(scenario_id)
        if not scenario:
            flash('找不到指定的场景', 'danger')
            return redirect(url_for('admin_scenarios'))
        
        # 切换场景状态
        try:
            current_status = scenario.get('is_active', True)
            new_status = not current_status
            
            if manager.update_scenario(
                scenario_id=scenario_id,
                is_active=new_status
            ):
                status_text = "启用" if new_status else "禁用"
                flash(f'成功{status_text}场景：{scenario["display_name"]}', 'success')
            else:
                flash('更新场景状态失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'更新场景状态时出错：{str(e)}', 'danger')
        
        return redirect(url_for('admin_scenarios'))
    
    # 用户管理相关路由
    @app.route('/admin/users')
    @login_required
    @db_required
    def users_list():
        """用户管理页面 - 显示所有用户列表"""
        manager = get_crawler_config_manager()
        users = manager.get_all_users()
        return render_template('admin/users.html', users=users)
    
    @app.route('/admin/users/<int:user_id>')
    @login_required
    @db_required
    def user_detail(user_id):
        """用户详情页面"""
        manager = get_crawler_config_manager()
        user = manager.get_user_by_id(user_id)
        
        if not user:
            flash('找不到指定用户', 'danger')
            return redirect(url_for('users_list'))
            
        return render_template('admin/user_detail.html', user=user)
    
    @app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
    @login_required
    @db_required
    def user_edit(user_id):
        """编辑用户信息"""
        manager = get_crawler_config_manager()
        user = manager.get_user_by_id(user_id)
        
        if not user:
            flash('找不到指定用户', 'danger')
            return redirect(url_for('users_list'))
        
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email')
            phone = request.form.get('phone')
            is_active = request.form.get('is_active') == 'on'
            
            # 更新密码（如果提供）
            password = request.form.get('password')
            if password and password.strip():
                # 更新密码
                success = manager.change_user_password(user_id, password)
                if not success:
                    flash('更新密码失败', 'danger')
            
            # 更新用户信息
            success = manager.update_user(user_id, username, email, phone, is_active)
            
            if success:
                flash('用户信息已更新', 'success')
                return redirect(url_for('users_list'))
            else:
                flash('更新用户信息失败', 'danger')
        
        return render_template('admin/user_edit.html', user=user)
    
    @app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
    @login_required
    @db_required
    def user_delete(user_id):
        """删除用户"""
        manager = get_crawler_config_manager()
        
        # 检查用户是否存在
        user = manager.get_user_by_id(user_id)
        if not user:
            flash('找不到指定用户', 'danger')
            return redirect(url_for('users_list'))
        
        # 删除用户
        success = manager.delete_user(user_id)
        
        if success:
            flash('用户已删除', 'success')
        else:
            flash('删除用户失败', 'danger')
            
        return redirect(url_for('users_list'))
    
    @app.route('/admin/users/add', methods=['GET', 'POST'])
    @login_required
    @db_required
    def user_add():
        """添加新用户"""
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            phone = request.form.get('phone')
            email = request.form.get('email', '')
            is_active = request.form.get('is_active') == 'on'
            
            if not username or not password or not phone:
                flash('用户名、密码和手机号不能为空', 'danger')
                return render_template('admin/user_add.html')
            
            manager = get_crawler_config_manager()
            user_id = manager.create_user(username, password, phone, email, is_active)
            
            if user_id:
                flash('用户创建成功', 'success')
                return redirect(url_for('users_list'))
            else:
                flash('创建用户失败', 'danger')
                
        return render_template('admin/user_add.html')
    
    # 注册API端点
    @app.route('/api/send-verification-code', methods=['POST'])
    def send_verification_code():
        """发送验证码API"""
        data = request.json
        if not data or 'phone' not in data or 'purpose' not in data:
            return jsonify({'status': 'error', 'message': '缺少必要参数'}), 400
            
        phone = data['phone']
        purpose = data['purpose']
        
        # 验证用途
        valid_purposes = ['register', 'login', 'reset']
        if purpose not in valid_purposes:
            return jsonify({'status': 'error', 'message': '无效的验证码用途'}), 400
            
        # 检查手机号格式
        if not phone or len(phone) != 11 or not phone.isdigit():
            return jsonify({'status': 'error', 'message': '无效的手机号码'}), 400
            
        # 获取数据库管理器
        manager = get_crawler_config_manager()
        if not manager:
            return jsonify({'status': 'error', 'message': '服务器内部错误'}), 500
            
        # 生成验证码
        code = manager.generate_verification_code()
        
        # 保存验证码
        saved = manager.save_verification_code(phone, code, purpose)
        if not saved:
            return jsonify({'status': 'error', 'message': '验证码保存失败'}), 500
            
        # 模拟发送短信
        # 在实际环境中，这里应该对接真实的SMS服务
        # 此处为了演示，只记录日志
        logger.info(f"向 {phone} 发送验证码: {code}，用途: {purpose}")
        
        # 返回成功
        return jsonify({
            'status': 'success', 
            'message': '验证码已发送',
            'debug_code': code  # 仅用于开发测试，实际环境应移除
        })
    
    @app.route('/api/login', methods=['POST'])
    def api_login():
        """用户登录API"""
        data = request.json
        if not data:
            return jsonify({'status': 'error', 'message': '无效请求'}), 400
            
        login_type = data.get('type')
        
        # 获取数据库管理器
        manager = get_crawler_config_manager()
        if not manager:
            return jsonify({'status': 'error', 'message': '服务器内部错误'}), 500
            
        if login_type == 'password':
            # 密码登录
            phone = data.get('phone')
            password = data.get('password')
            
            if not phone or not password:
                return jsonify({'status': 'error', 'message': '手机号和密码不能为空'}), 400
                
            # 验证用户
            from src.app.client_user_manager import ClientUserManager
            user_manager = ClientUserManager()
            user = user_manager.authenticate_user(phone, password)
            
            if not user:
                return jsonify({'status': 'error', 'message': '手机号或密码错误'}), 401
                
            # 登录成功，生成token
            token = user_manager.generate_token(user['id'])
            
            return jsonify({
                'status': 'success',
                'message': '登录成功',
                'token': token,
                'user': {
                    'id': user['id'],
                    'phone': user['phone'],
                    'username': user.get('username')
                }
            })
            
        elif login_type == 'code':
            # 验证码登录
            phone = data.get('phone')
            code = data.get('code')
            
            if not phone or not code:
                return jsonify({'status': 'error', 'message': '手机号和验证码不能为空'}), 400
                
            # 验证验证码
            if not manager.verify_code(phone, code, 'login'):
                return jsonify({'status': 'error', 'message': '验证码无效或已过期'}), 401
                
            # 验证通过，获取用户信息
            from src.app.client_user_manager import ClientUserManager
            user_manager = ClientUserManager()
            user = user_manager.get_user_by_phone(phone)
            
            if not user:
                return jsonify({'status': 'error', 'message': '用户不存在'}), 401
                
            # 生成token
            token = user_manager.generate_token(user['id'])
            
            return jsonify({
                'status': 'success',
                'message': '登录成功',
                'token': token,
                'user': {
                    'id': user['id'],
                    'phone': user['phone'],
                    'username': user.get('username')
                }
            })
        else:
            return jsonify({'status': 'error', 'message': '不支持的登录类型'}), 400
    
    @app.route('/api/register', methods=['POST'])
    def api_register():
        """用户注册API"""
        data = request.json
        if not data:
            return jsonify({'status': 'error', 'message': '无效请求'}), 400
            
        phone = data.get('phone')
        password = data.get('password')
        code = data.get('code')
        username = data.get('username')
        email = data.get('email')
        
        if not phone or not password or not code:
            return jsonify({'status': 'error', 'message': '手机号、密码和验证码不能为空'}), 400
            
        # 获取数据库管理器
        manager = get_crawler_config_manager()
        if not manager:
            return jsonify({'status': 'error', 'message': '服务器内部错误'}), 500
            
        # 验证验证码
        if not manager.verify_code(phone, code, 'register'):
            return jsonify({'status': 'error', 'message': '验证码无效或已过期'}), 401
            
        # 注册用户
        from src.app.client_user_manager import ClientUserManager
        user_manager = ClientUserManager()
        
        # 检查手机号是否已注册
        existing_user = user_manager.get_user_by_phone(phone)
        if existing_user:
            return jsonify({'status': 'error', 'message': '该手机号已注册'}), 400
            
        # 注册新用户
        user_id = user_manager.register_user(phone, password, username, email)
        
        if not user_id:
            return jsonify({'status': 'error', 'message': '用户注册失败'}), 500
            
        # 生成token
        token = user_manager.generate_token(user_id)
        
        return jsonify({
            'status': 'success',
            'message': '注册成功',
            'token': token,
            'user': {
                'id': user_id,
                'phone': phone,
                'username': username
            }
        })
    
    @app.route('/api/logout', methods=['POST'])
    def api_logout():
        """用户登出API"""
        # 由于使用的是JWT令牌，服务器端不需要执行特殊操作
        # 客户端应删除本地存储的令牌
        
        return jsonify({
            'status': 'success',
            'message': '已成功退出登录'
        })
    
    # 直接 URL 管理路由
    @app.route('/admin/direct-urls')
    @login_required
    @db_required
    def admin_direct_urls():
        # Get all direct URLs
        manager = get_crawler_config_manager()
        try:
            direct_urls = manager.get_all_direct_urls_with_scenario()
        except Exception as e:
            flash(f'加载直接爬取URL数据时出错: {str(e)}', 'danger')
            direct_urls = []
        
        # Get all scenarios for filtering
        scenarios = manager.get_all_scenarios()
        
        return render_template('direct_urls.html', active_page='direct_urls', 
                               direct_urls=direct_urls, scenarios=scenarios)


    @app.route('/admin/direct-urls/add', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_add_direct_url():
        # Get all scenarios
        manager = get_crawler_config_manager()
        scenarios = manager.get_all_scenarios()
        
        if request.method == 'POST':
            # Get form data
            scenario_id = request.form.get('scenario_id')
            url = request.form.get('url')
            description = request.form.get('description', '')
            
            # Validate data
            if not scenario_id or not url:
                flash('所有必填字段都必须填写', 'danger')
                return render_template('direct_url_form.html', active_page='direct_urls', 
                                      title='添加直接爬取URL', scenarios=scenarios)
            
            try:
                # Add direct URL to database
                direct_url_id = manager.add_direct_url(
                    scenario_id=int(scenario_id),
                    url=url,
                    description=description
                )
                
                if direct_url_id:
                    flash(f'成功添加直接爬取URL', 'success')
                    return redirect(url_for('admin_direct_urls'))
                else:
                    flash('添加直接爬取URL失败，请稍后再试', 'danger')
            except Exception as e:
                flash(f'添加直接爬取URL时出错：{str(e)}', 'danger')
        
        return render_template('direct_url_form.html', active_page='direct_urls', 
                              title='添加直接爬取URL', scenarios=scenarios)


    @app.route('/admin/direct-urls/edit/<int:direct_url_id>', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_edit_direct_url(direct_url_id):
        # Get direct URL data
        manager = get_crawler_config_manager()
        direct_url = manager.get_direct_url_by_id(direct_url_id)
        
        if not direct_url:
            flash('找不到指定的直接爬取URL', 'danger')
            return redirect(url_for('admin_direct_urls'))
        
        # Get all scenarios
        scenarios = manager.get_all_scenarios()
        
        if request.method == 'POST':
            # Get form data
            url = request.form.get('url')
            description = request.form.get('description', '')
            is_active = True if request.form.get('is_active') else False
            
            # Validate data
            if not url:
                flash('所有必填字段都必须填写', 'danger')
                return render_template('direct_url_form.html', active_page='direct_urls', 
                                      title='编辑直接爬取URL', direct_url=direct_url, 
                                      scenarios=scenarios, edit_mode=True)
            
            try:
                # 检查场景是否已更改
                if int(request.form.get('scenario_id')) != direct_url['scenario_id']:
                    # 如果场景已更改，需要删除旧记录并创建新记录
                    # 先删除旧记录
                    manager.delete_direct_url(direct_url_id)
                    
                    # 创建新记录
                    new_direct_url_id = manager.add_direct_url(
                        scenario_id=int(request.form.get('scenario_id')),
                        url=url,
                        description=description
                    )
                    
                    if new_direct_url_id:
                        # 如果需要设置为非活动状态
                        if not is_active:
                            manager.update_direct_url(
                                direct_url_id=new_direct_url_id,
                                is_active=False
                            )
                        flash(f'成功更新直接爬取URL并更改了所属场景', 'success')
                        return redirect(url_for('admin_direct_urls'))
                    else:
                        flash('更新直接爬取URL失败，请稍后再试', 'danger')
                else:
                    # 如果场景未更改，直接更新其他字段
                    result = manager.update_direct_url(
                        direct_url_id=direct_url_id,
                        url=url,
                        description=description,
                        is_active=is_active
                    )
                    
                    if result:
                        flash(f'成功更新直接爬取URL', 'success')
                        return redirect(url_for('admin_direct_urls'))
                    else:
                        flash('更新直接爬取URL失败，请稍后再试', 'danger')
            except Exception as e:
                flash(f'更新直接爬取URL时出错：{str(e)}', 'danger')
        
        return render_template('direct_url_form.html', active_page='direct_urls', 
                              title='编辑直接爬取URL', direct_url=direct_url, 
                              scenarios=scenarios, edit_mode=True)


    @app.route('/admin/direct-urls/delete/<int:direct_url_id>', methods=['POST'])
    @login_required
    @db_required
    def admin_delete_direct_url(direct_url_id):
        """删除直接爬取URL"""
        manager = get_crawler_config_manager()
        
        # 获取直接URL信息
        direct_url = manager.get_direct_url_by_id(direct_url_id)
        if not direct_url:
            flash('找不到指定的直接爬取URL', 'danger')
            return redirect(url_for('admin_direct_urls'))
        
        # 删除直接URL
        try:
            if manager.delete_direct_url(direct_url_id):
                flash(f'成功删除直接爬取URL', 'success')
            else:
                flash('删除直接爬取URL失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'删除直接爬取URL时出错：{str(e)}', 'danger')
        
        return redirect(url_for('admin_direct_urls'))


    @app.route('/admin/direct-urls/toggle/<int:direct_url_id>', methods=['POST'])
    @login_required
    @db_required
    def admin_toggle_direct_url(direct_url_id):
        """启用或禁用直接爬取URL"""
        manager = get_crawler_config_manager()
        
        # 检查直接URL是否存在
        direct_url = manager.get_direct_url_by_id(direct_url_id)
        if not direct_url:
            flash('找不到指定的直接爬取URL', 'danger')
            return redirect(url_for('admin_direct_urls'))
        
        # 切换直接URL状态
        try:
            current_status = direct_url.get('is_active', True)
            new_status = not current_status
            
            if manager.update_direct_url(
                direct_url_id=direct_url_id,
                is_active=new_status
            ):
                status_text = "启用" if new_status else "禁用"
                title = direct_url.get('title', '未命名URL')
                flash(f'成功{status_text}直接爬取URL：{title}', 'success')
            else:
                flash('更新直接爬取URL状态失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'更新直接爬取URL状态时出错：{str(e)}', 'danger')
        
        return redirect(url_for('admin_direct_urls'))
        
    # 定时爬虫任务管理路由
    @app.route('/admin/scheduled_tasks')
    @login_required
    @db_required
    def admin_scheduled_tasks():
        """定时爬虫任务管理页面"""
        manager = get_crawler_config_manager()
        tasks = manager.get_all_scheduled_tasks()
        scenarios = manager.get_all_scenarios()
        platforms = manager.get_all_platforms()
        
        # 解析JSON格式的关键词和平台
        for task in tasks:
            if task.get('keywords'):
                try:
                    task['keywords_list'] = json.loads(task['keywords'])
                except:
                    task['keywords_list'] = []
            else:
                task['keywords_list'] = []
                
            if task.get('platforms'):
                try:
                    task['platforms_list'] = json.loads(task['platforms'])
                except:
                    task['platforms_list'] = []
            else:
                task['platforms_list'] = []
        
        return render_template('admin/scheduled_tasks.html', 
                            active_page='scheduled_tasks', 
                            tasks=tasks,
                            scenarios=scenarios,
                            platforms=platforms)


    @app.route('/admin/scheduled_tasks/add', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_add_scheduled_task():
        """添加定时爬虫任务"""
        manager = get_crawler_config_manager()
        scenarios = manager.get_all_scenarios()
        platforms = manager.get_all_platforms()
        
        if request.method == 'POST':
            # 获取表单数据
            task_name = request.form.get('task_name')
            scenario_id = request.form.get('scenario_id')
            keywords_str = request.form.get('keywords', '')
            cron_expression = request.form.get('cron_expression')
            max_concurrent_tasks = request.form.get('max_concurrent_tasks', 3)
            description = request.form.get('description', '')
            is_active = 'is_active' in request.form
            
            # 验证数据
            if not task_name or not scenario_id or not keywords_str or not cron_expression:
                flash('所有必填字段都必须填写', 'danger')
                return render_template('admin/scheduled_task_form.html', 
                                    active_page='scheduled_tasks',
                                    title='添加定时爬虫任务',
                                    scenarios=scenarios,
                                    platforms=platforms)
            
            try:
                # 处理关键词列表
                keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                
                # 处理平台列表
                selected_platforms = request.form.getlist('selected_platforms')
                
                # 检查是否选择了平台
                if not selected_platforms:
                    flash('请至少选择一个平台', 'danger')
                    return render_template('admin/scheduled_task_form.html', 
                                        active_page='scheduled_tasks',
                                        title='添加定时爬虫任务',
                                        scenarios=scenarios,
                                        platforms=platforms)
                
                # 添加任务到数据库
                task_id = manager.add_scheduled_task(
                    task_name=task_name,
                    scenario_id=scenario_id,
                    keywords=keywords,
                    platforms=selected_platforms,
                    cron_expression=cron_expression,
                    max_concurrent_tasks=int(max_concurrent_tasks),
                    description=description,
                    is_active=is_active
                )
                
                if task_id:
                    flash(f'成功添加定时爬虫任务：{task_name}', 'success')
                    return redirect(url_for('admin_scheduled_tasks'))
                else:
                    flash('添加定时爬虫任务失败，请稍后再试', 'danger')
            except Exception as e:
                flash(f'添加定时爬虫任务时出错：{str(e)}', 'danger')
        
        return render_template('admin/scheduled_task_form.html', 
                            active_page='scheduled_tasks',
                            title='添加定时爬虫任务',
                            scenarios=scenarios,
                            platforms=platforms)


    @app.route('/admin/scheduled_tasks/edit/<int:task_id>', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_edit_scheduled_task(task_id):
        """编辑定时爬虫任务"""
        # 获取任务数据
        manager = get_crawler_config_manager()
        task = manager.get_scheduled_task(task_id)
        scenarios = manager.get_all_scenarios()
        platforms = manager.get_all_platforms()
        
        if not task:
            flash('找不到指定的定时爬虫任务', 'danger')
            return redirect(url_for('admin_scheduled_tasks'))
        
        # 解析JSON格式的关键词和平台
        if task.get('keywords'):
            try:
                task['keywords_list'] = json.loads(task['keywords'])
                task['keywords_str'] = ', '.join(task['keywords_list'])
            except:
                task['keywords_list'] = []
                task['keywords_str'] = ''
        else:
            task['keywords_list'] = []
            task['keywords_str'] = ''
            
        if task.get('platforms'):
            try:
                task['platforms_list'] = json.loads(task['platforms'])
            except:
                task['platforms_list'] = []
        else:
            task['platforms_list'] = []
        
        if request.method == 'POST':
            # 获取表单数据
            task_name = request.form.get('task_name')
            scenario_id = request.form.get('scenario_id')
            keywords_str = request.form.get('keywords', '')
            cron_expression = request.form.get('cron_expression')
            max_concurrent_tasks = request.form.get('max_concurrent_tasks', 3)
            description = request.form.get('description', '')
            is_active = 'is_active' in request.form
            
            # 验证数据
            if not task_name or not scenario_id or not keywords_str or not cron_expression:
                flash('所有必填字段都必须填写', 'danger')
                return render_template('admin/scheduled_task_form.html', 
                                    active_page='scheduled_tasks',
                                    title='编辑定时爬虫任务',
                                    task=task,
                                    edit_mode=True,
                                    scenarios=scenarios,
                                    platforms=platforms)
            
            try:
                # 处理关键词列表
                keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
                
                # 处理平台列表
                selected_platforms = request.form.getlist('selected_platforms')
                
                # 检查是否选择了平台
                if not selected_platforms:
                    flash('请至少选择一个平台', 'danger')
                    return render_template('admin/scheduled_task_form.html', 
                                        active_page='scheduled_tasks',
                                        title='编辑定时爬虫任务',
                                        task=task,
                                        edit_mode=True,
                                        scenarios=scenarios,
                                        platforms=platforms)
                
                # 更新任务
                success = manager.update_scheduled_task(
                    task_id=task_id,
                    task_name=task_name,
                    scenario_id=scenario_id,
                    keywords=keywords,
                    platforms=selected_platforms,
                    cron_expression=cron_expression,
                    max_concurrent_tasks=int(max_concurrent_tasks),
                    description=description,
                    is_active=is_active
                )
                
                if success:
                    flash(f'成功更新定时爬虫任务：{task_name}', 'success')
                    return redirect(url_for('admin_scheduled_tasks'))
                else:
                    flash('更新定时爬虫任务失败，请稍后再试', 'danger')
            except Exception as e:
                flash(f'更新定时爬虫任务时出错：{str(e)}', 'danger')
        
        return render_template('admin/scheduled_task_form.html', 
                            active_page='scheduled_tasks',
                            title='编辑定时爬虫任务',
                            task=task,
                            edit_mode=True,
                            scenarios=scenarios,
                            platforms=platforms)


    @app.route('/admin/scheduled_tasks/delete/<int:task_id>', methods=['POST'])
    @login_required
    @db_required
    def admin_delete_scheduled_task(task_id):
        """删除定时爬虫任务"""
        manager = get_crawler_config_manager()
        
        # 获取任务信息（用于日志记录）
        task = manager.get_scheduled_task(task_id)
        if not task:
            flash('找不到指定的定时爬虫任务', 'danger')
            return redirect(url_for('admin_scheduled_tasks'))
        
        # 执行删除操作
        success = manager.delete_scheduled_task(task_id)
        
        if success:
            flash(f'成功删除定时爬虫任务：{task["task_name"]}', 'success')
        else:
            flash('删除定时爬虫任务失败，请稍后再试', 'danger')
        
        return redirect(url_for('admin_scheduled_tasks'))


    @app.route('/admin/scheduled_tasks/toggle/<int:task_id>', methods=['POST'])
    @login_required
    @db_required
    def admin_toggle_scheduled_task(task_id):
        """切换定时爬虫任务的启用状态"""
        manager = get_crawler_config_manager()
        
        # 获取任务信息（用于日志和消息）
        task = manager.get_scheduled_task(task_id)
        if not task:
            flash('找不到指定的定时爬虫任务', 'danger')
            return redirect(url_for('admin_scheduled_tasks'))
        
        # 执行状态切换
        success = manager.toggle_scheduled_task_status(task_id)
        
        if success:
            new_status = not task['is_active']
            status_text = '启用' if new_status else '禁用'
            flash(f'成功{status_text}定时爬虫任务：{task["task_name"]}', 'success')
        else:
            flash('切换定时爬虫任务状态失败，请稍后再试', 'danger')
        
        return redirect(url_for('admin_scheduled_tasks'))
        
    # 平台管理路由
    @app.route('/admin/platforms')
    @login_required
    @db_required
    def admin_platforms():
        """平台管理页面"""
        # 获取所有平台
        manager = get_crawler_config_manager()
        try:
            platforms = manager.get_all_platforms()
        except Exception as e:
            flash(f'加载平台数据时出错: {str(e)}', 'danger')
            platforms = []
        
        return render_template('admin/platforms.html', active_page='platforms', platforms=platforms)
    
    
    @app.route('/admin/platforms/add', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_add_platform():
        """添加平台"""
        if request.method == 'POST':
            # 获取表单数据
            name = request.form.get('name')
            display_name = request.form.get('display_name')
            description = request.form.get('description', '')
            
            # 验证数据
            if not name or not display_name:
                flash('所有必填字段都必须填写', 'danger')
                return render_template('admin/platform_form.html', active_page='platforms', title='添加平台')
            
            try:
                # 添加平台到数据库
                manager = get_crawler_config_manager()
                platform_id = manager.add_platform(
                    name=name,
                    display_name=display_name,
                    description=description
                )
                
                if platform_id:
                    flash(f'成功添加平台：{display_name}', 'success')
                    return redirect(url_for('admin_platforms'))
                else:
                    flash('添加平台失败，请稍后再试', 'danger')
            except Exception as e:
                flash(f'添加平台时出错：{str(e)}', 'danger')
        
        return render_template('admin/platform_form.html', active_page='platforms', title='添加平台')
    
    
    @app.route('/admin/platforms/edit/<int:platform_id>', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_edit_platform(platform_id):
        """编辑平台"""
        # 获取平台数据
        manager = get_crawler_config_manager()
        platform = manager.get_platform_by_id(platform_id)
        
        if not platform:
            flash('找不到指定的平台', 'danger')
            return redirect(url_for('admin_platforms'))
        
        if request.method == 'POST':
            # 获取表单数据
            display_name = request.form.get('display_name')
            description = request.form.get('description', '')
            is_active = True if request.form.get('is_active') else False
            
            # 验证数据
            if not display_name:
                flash('所有必填字段都必须填写', 'danger')
                return render_template('admin/platform_form.html', active_page='platforms', 
                                     title='编辑平台', platform=platform, edit_mode=True)
            
            try:
                # 更新平台数据
                result = manager.update_platform(
                    platform_id=platform_id,
                    display_name=display_name,
                    description=description,
                    is_active=is_active
                )
                
                if result:
                    flash(f'成功更新平台：{display_name}', 'success')
                    return redirect(url_for('admin_platforms'))
                else:
                    flash('更新平台失败，请稍后再试', 'danger')
            except Exception as e:
                flash(f'更新平台时出错：{str(e)}', 'danger')
        
        return render_template('admin/platform_form.html', active_page='platforms', 
                             title='编辑平台', platform=platform, edit_mode=True)
    
    
    @app.route('/admin/platforms/delete/<int:platform_id>', methods=['POST'])
    @login_required
    @db_required
    def admin_delete_platform(platform_id):
        """删除平台"""
        manager = get_crawler_config_manager()
        
        # 检查平台是否存在
        platform = manager.get_platform_by_id(platform_id)
        if not platform:
            flash('找不到指定的平台', 'danger')
            return redirect(url_for('admin_platforms'))
        
        # 删除平台
        try:
            if manager.delete_platform(platform_id):
                flash(f'成功删除平台：{platform["display_name"]}', 'success')
            else:
                flash('删除平台失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'删除平台时出错：{str(e)}', 'danger')
        
        return redirect(url_for('admin_platforms'))
    
    
    @app.route('/admin/platforms/toggle/<int:platform_id>', methods=['POST'])
    @login_required
    @db_required
    def admin_toggle_platform(platform_id):
        """启用或禁用平台"""
        manager = get_crawler_config_manager()
        
        # 检查平台是否存在
        platform = manager.get_platform_by_id(platform_id)
        if not platform:
            flash('找不到指定的平台', 'danger')
            return redirect(url_for('admin_platforms'))
        
        # 切换平台状态
        try:
            current_status = platform.get('is_active', True)
            new_status = not current_status
            
            if manager.update_platform(
                platform_id=platform_id,
                is_active=new_status
            ):
                status_text = "启用" if new_status else "禁用"
                flash(f'成功{status_text}平台：{platform["display_name"]}', 'success')
            else:
                flash('更新平台状态失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'更新平台状态时出错：{str(e)}', 'danger')
        
        return redirect(url_for('admin_platforms'))
        
    # URL 格式管理路由
    @app.route('/admin/url-formats')
    @login_required
    @db_required
    def admin_url_formats():
        # Get all URL formats
        manager = get_crawler_config_manager()
        try:
            url_formats = manager.get_all_url_formats_with_scenario()
        except Exception as e:
            flash(f'加载URL格式数据时出错: {str(e)}', 'danger')
            url_formats = []
        
        # Get all scenarios for filtering
        scenarios = manager.get_all_scenarios()
        
        return render_template('url_formats.html', active_page='url_formats', 
                              url_formats=url_formats, scenarios=scenarios)


    @app.route('/admin/url-formats/add', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_add_url_format():
        # Get all scenarios
        manager = get_crawler_config_manager()
        scenarios = manager.get_all_scenarios()
        
        # Get all platforms
        platforms = manager.get_all_platforms()
        
        if request.method == 'POST':
            # Get form data
            scenario_id = request.form.get('scenario_id')
            platform = request.form.get('platform')
            url_format = request.form.get('url_format')
            description = request.form.get('description', '')
            
            # Validate data
            if not scenario_id or not platform or not url_format:
                flash('所有必填字段都必须填写', 'danger')
                return render_template('url_format_form.html', active_page='url_formats', 
                                     title='添加搜索URL格式', scenarios=scenarios, platforms=platforms)
            
            try:
                # Add URL format to database
                url_format_id = manager.add_url_format(
                    scenario_id=int(scenario_id),
                    platform=platform,
                    url_format=url_format,
                    description=description
                )
                
                if url_format_id:
                    flash(f'成功添加搜索URL格式', 'success')
                    return redirect(url_for('admin_url_formats'))
                else:
                    flash('添加搜索URL格式失败，请稍后再试', 'danger')
            except Exception as e:
                flash(f'添加搜索URL格式时出错：{str(e)}', 'danger')
        
        return render_template('url_format_form.html', active_page='url_formats', 
                             title='添加搜索URL格式', scenarios=scenarios, platforms=platforms)


    @app.route('/admin/url-formats/edit/<int:url_format_id>', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_edit_url_format(url_format_id):
        # Get URL format data
        manager = get_crawler_config_manager()
        url_format = manager.get_url_format_by_id(url_format_id)
        
        if not url_format:
            flash('找不到指定的搜索URL格式', 'danger')
            return redirect(url_for('admin_url_formats'))
        
        # Get all scenarios
        scenarios = manager.get_all_scenarios()
        
        # Get all platforms
        platforms = manager.get_all_platforms()
        
        if request.method == 'POST':
            # Get form data
            scenario_id = request.form.get('scenario_id')
            platform = request.form.get('platform')
            url_format_str = request.form.get('url_format')
            description = request.form.get('description', '')
            is_active = True if request.form.get('is_active') else False
            
            # 转换为整数，方便比较
            scenario_id = int(scenario_id) if scenario_id else None
            
            # Validate data
            if not scenario_id or not platform or not url_format_str:
                flash('所有必填字段都必须填写', 'danger')
                return render_template('url_format_form.html', active_page='url_formats', 
                                     title='编辑搜索URL格式', url_format=url_format, 
                                     scenarios=scenarios, platforms=platforms, edit_mode=True)
            
            try:
                # 检查场景ID或平台是否已更改
                changed_scenario = scenario_id != url_format['scenario_id']
                changed_platform = platform != url_format['platform']
                
                # 只在场景ID或平台变化时才需要处理潜在的重复问题
                if changed_scenario or changed_platform:
                    with manager.connection.cursor() as cursor:
                        # 检查是否存在相同scenario_id和platform的其他记录
                        cursor.execute(
                            """
                            SELECT id 
                            FROM crawler_url_formats 
                            WHERE scenario_id = %s AND platform = %s AND id != %s
                            """, 
                            (scenario_id, platform, url_format_id)
                        )
                        duplicate = cursor.fetchone()
                        
                        if duplicate:
                            # 存在重复记录，先更新当前记录的所有非主键字段
                            cursor.execute(
                                """
                                UPDATE crawler_url_formats
                                SET url_format = %s, description = %s, is_active = %s
                                WHERE id = %s
                                """,
                                (url_format_str, description, is_active, url_format_id)
                            )
                            
                            # 删除重复记录
                            cursor.execute("DELETE FROM crawler_url_formats WHERE id = %s", (duplicate['id'],))
                            
                            # 更新当前记录的scenario_id和platform字段
                            cursor.execute(
                                """
                                UPDATE crawler_url_formats
                                SET scenario_id = %s, platform = %s
                                WHERE id = %s
                                """,
                                (scenario_id, platform, url_format_id)
                            )
                            
                            manager.connection.commit()
                            flash('成功更新搜索URL格式，替换了已存在的记录', 'success')
                            return redirect(url_for('admin_url_formats'))
                
                # 更新当前记录
                with manager.connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE crawler_url_formats
                        SET scenario_id = %s, platform = %s, url_format = %s, description = %s, is_active = %s
                        WHERE id = %s
                        """,
                        (scenario_id, platform, url_format_str, description, is_active, url_format_id)
                    )
                    affected_rows = cursor.rowcount
                    manager.connection.commit()
                    
                    if affected_rows > 0:
                        flash('成功更新搜索URL格式', 'success')
                        return redirect(url_for('admin_url_formats'))
                    else:
                        flash('更新搜索URL格式失败，请稍后再试', 'danger')
                        
            except Exception as e:
                flash(f'更新搜索URL格式时出错：{str(e)}', 'danger')
        
        return render_template('url_format_form.html', active_page='url_formats', 
                             title='编辑搜索URL格式', url_format=url_format, 
                             scenarios=scenarios, platforms=platforms, edit_mode=True)


    @app.route('/admin/url-formats/delete/<int:url_format_id>', methods=['POST'])
    @login_required
    @db_required
    def admin_delete_url_format(url_format_id):
        """删除URL格式"""
        manager = get_crawler_config_manager()
        
        # 获取URL格式信息
        url_format = manager.get_url_format_by_id(url_format_id)
        if not url_format:
            flash('找不到指定的URL格式', 'danger')
            return redirect(url_for('admin_url_formats'))
        
        # 删除URL格式
        try:
            if manager.delete_url_format(url_format_id):
                # 使用platform字段而不是name字段，因为后者可能不存在
                platform_name = url_format.get('platform', '未知平台')
                flash(f'成功删除URL格式：{platform_name}', 'success')
            else:
                flash('删除URL格式失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'删除URL格式时出错：{str(e)}', 'danger')
        
        return redirect(url_for('admin_url_formats'))


    @app.route('/admin/url-formats/toggle/<int:url_format_id>', methods=['POST'])
    @login_required
    @db_required
    def admin_toggle_url_format(url_format_id):
        """启用或禁用URL格式"""
        manager = get_crawler_config_manager()
        
        # 检查URL格式是否存在
        url_format = manager.get_url_format_by_id(url_format_id)
        if not url_format:
            flash('找不到指定的URL格式', 'danger')
            return redirect(url_for('admin_url_formats'))
        
        # 切换URL格式状态
        try:
            current_status = url_format.get('is_active', True)
            new_status = not current_status
            
            if manager.update_url_format(
                url_format_id=url_format_id,
                is_active=new_status
            ):
                status_text = "启用" if new_status else "禁用"
                # 使用platform字段代替name字段，因为数据库中没有name字段
                platform_name = url_format.get('platform', '未知平台')
                flash(f'成功{status_text} URL格式：{platform_name}', 'success')
            else:
                flash('更新URL格式状态失败，请稍后再试', 'danger')
        except Exception as e:
            flash(f'更新URL格式状态时出错：{str(e)}', 'danger')
        
        return redirect(url_for('admin_url_formats'))
        
    # =============== 短信验证码相关函数 ===============
    def generate_verification_code():
        """生成6位数字验证码"""
        return ''.join(random.choices('0123456789', k=6))


    def send_sms_code(phone, code):
        """
        发送短信验证码（模拟）
        
        Args:
            phone: 手机号
            code: 验证码
        
        Returns:
            bool: 是否发送成功
        """
        try:
            # 这里应该是实际发送短信的代码
            # 模拟实现，总是返回成功
            print(f"[模拟] 发送验证码到 {phone}: {code}")
            return True
        except Exception as e:
            print(f"发送验证码失败: {str(e)}")
            return False


    # =============== 用户管理相关路由 ===============
    @app.route('/admin/users')
    @login_required
    @db_required
    def admin_users_list():
        """用户管理页面 - 显示所有用户列表"""
        manager = get_crawler_config_manager()
        try:
            users = manager.get_all_admin_users()
            return render_template('users.html', active_page='users', users=users)
        except Exception as e:
            flash(f'加载用户数据时出错: {str(e)}', 'danger')
            return redirect(url_for('index'))


    @app.route('/admin/users/<int:user_id>')
    @login_required
    @db_required
    def admin_user_detail(user_id):
        """用户详情页面"""
        manager = get_crawler_config_manager()
        try:
            user = manager.get_admin_user_by_id(user_id)
            if not user:
                flash('用户不存在', 'danger')
                return redirect(url_for('admin_users_list'))
            
            return render_template('user_detail.html', active_page='users', user=user)
        except Exception as e:
            flash(f'加载用户数据时出错: {str(e)}', 'danger')
            return redirect(url_for('admin_users_list'))


    @app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_user_edit(user_id):
        """编辑用户信息"""
        manager = get_crawler_config_manager()
        
        try:
            user = manager.get_admin_user_by_id(user_id)
            if not user:
                flash('用户不存在', 'danger')
                return redirect(url_for('admin_users_list'))
            
            if request.method == 'POST':
                username = request.form.get('username')
                email = request.form.get('email')
                phone = request.form.get('phone')
                is_active = request.form.get('is_active') == 'on'
                
                # 验证输入
                if not phone or len(phone) != 11 or not phone.isdigit():
                    flash('请输入有效的手机号码', 'danger')
                    return render_template('user_edit.html', active_page='users', user=user)
                
                # 检查电话号码是否已被其他用户使用
                existing_user = manager.get_admin_user_by_phone(phone)
                if existing_user and existing_user['id'] != user_id:
                    flash('该手机号已被其他用户使用', 'danger')
                    return render_template('user_edit.html', active_page='users', user=user)
                
                # 更新用户信息
                success = manager.update_admin_user(
                    user_id=user_id,
                    username=username,
                    email=email,
                    phone=phone,
                    is_active=is_active
                )
                
                if success:
                    flash('用户信息更新成功', 'success')
                    return redirect(url_for('admin_user_detail', user_id=user_id))
                else:
                    flash('更新用户信息失败', 'danger')
            
            return render_template('user_edit.html', active_page='users', user=user)
        except Exception as e:
            flash(f'处理用户数据时出错: {str(e)}', 'danger')
            return redirect(url_for('admin_users_list'))


    @app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
    @login_required
    @db_required
    def admin_user_delete(user_id):
        """删除用户"""
        manager = get_crawler_config_manager()
        
        try:
            # 检查是否是当前登录用户
            if session.get('admin_id') == user_id:
                flash('不能删除当前登录的用户', 'danger')
                return redirect(url_for('admin_users_list'))
            
            # 执行删除操作
            success = manager.delete_admin_user(user_id)
            if success:
                flash('用户已成功删除', 'success')
            else:
                flash('删除用户失败', 'danger')
        except Exception as e:
            flash(f'删除用户时出错: {str(e)}', 'danger')
        
        return redirect(url_for('admin_users_list'))


    @app.route('/admin/users/add', methods=['GET', 'POST'])
    @login_required
    @db_required
    def admin_user_add():
        """添加新用户"""
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email')
            phone = request.form.get('phone')
            password = request.form.get('password')
            
            # 验证输入
            if not phone or len(phone) != 11 or not phone.isdigit():
                flash('请输入有效的手机号码', 'danger')
                return render_template('user_add.html', active_page='users')
            
            if not password or len(password) < 6:
                flash('密码长度不能少于6个字符', 'danger')
                return render_template('user_add.html', active_page='users')
            
            manager = get_crawler_config_manager()
            
            # 检查电话号码是否已存在
            existing_user = manager.get_admin_user_by_phone(phone)
            if existing_user:
                flash('该手机号已被注册', 'danger')
                return render_template('user_add.html', active_page='users')
            
            # 如果提供了用户名，检查是否重复
            if username:
                existing_username = manager.get_admin_user_by_username(username)
                if existing_username:
                    flash('用户名已存在', 'danger')
                    return render_template('user_add.html', active_page='users')
            
            # 计算密码哈希
            hashed_password = hashlib.sha256(password.encode()).hexdigest()
            
            # 创建用户
            try:
                user_id = manager.create_admin_user_with_phone(
                    phone=phone,
                    password=hashed_password,
                    email=email,
                    username=username
                )
                
                if user_id:
                    flash('用户创建成功', 'success')
                    return redirect(url_for('admin_users_list'))
                else:
                    flash('用户创建失败', 'danger')
            except Exception as e:
                flash(f'创建用户时出错: {str(e)}', 'danger')
        
        return render_template('user_add.html', active_page='users')


    # =============== 用户验证码API ===============
    @app.route('/admin/api/user/send_code', methods=['POST'])
    def admin_send_verification_code():
        """发送验证码"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "无效的请求数据"}), 400
                
            phone = data.get('phone')
            purpose = data.get('purpose')
            
            # 检查手机号格式
            if not (phone and len(phone) == 11 and phone.isdigit()):
                return jsonify({"error": "无效的手机号格式"}), 400
            
            # 检查目的是否有效
            if purpose not in ["register", "login", "reset"]:
                return jsonify({"error": "无效的验证码用途"}), 400
            
            manager = get_crawler_config_manager()
            if not manager:
                return jsonify({"error": "数据库连接不可用"}), 500
                
            # 如果是注册，检查手机号是否已存在
            if purpose == "register":
                existing_user = manager.get_admin_user_by_phone(phone)
                if existing_user:
                    return jsonify({"error": "该手机号已注册"}), 400
            
            # 如果是登录或重置密码，检查手机号是否存在
            if purpose in ["login", "reset"]:
                existing_user = manager.get_admin_user_by_phone(phone)
                if not existing_user:
                    return jsonify({"error": "该手机号未注册"}), 404
            
            # 生成验证码
            code = generate_verification_code()
            
            # 保存验证码到数据库
            expires_at = datetime.now() + timedelta(minutes=10)  # 10分钟有效期
            manager.save_verification_code(phone, code, purpose, expires_at)
            
            # 发送验证码
            send_success = send_sms_code(phone, code)
            if not send_success:
                return jsonify({"error": "验证码发送失败"}), 500
            
            return jsonify({"message": "验证码已发送，10分钟内有效"}), 200
        
        except Exception as e:
            print(f"发送验证码失败: {str(e)}")
            return jsonify({"error": f"发送验证码失败: {str(e)}"}), 500


    # 用户注册API
    @app.route('/admin/api/user/register', methods=['POST'])
    def admin_api_register():
        """用户注册 API"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "无效的请求数据"}), 400
                
            phone = data.get('phone')
            code = data.get('code')
            password = data.get('password')
            email = data.get('email')
            username = data.get('username')
            
            if not phone or not code or not password:
                return jsonify({"error": "缺少必要参数"}), 400
            
            manager = get_crawler_config_manager()
            if not manager:
                return jsonify({"error": "数据库连接不可用"}), 500
            
            # 验证码是否有效
            verification = manager.verify_code(phone, code, "register")
            if not verification:
                return jsonify({"error": "验证码无效或已过期"}), 401
            
            # 检查手机号是否已存在
            existing_user = manager.get_admin_user_by_phone(phone)
            if existing_user:
                return jsonify({"error": "该手机号已注册"}), 400
            
            # 如果提供了用户名，检查是否重复
            if username:
                existing_username = manager.get_admin_user_by_username(username)
                if existing_username:
                    return jsonify({"error": "用户名已存在"}), 400
            
            # 计算密码哈希
            hashed_password = hash_password(password)
            
            # 标记验证码为已使用
            manager.mark_code_as_used(phone, code, "register")
            
            # 创建用户
            user_id = manager.create_admin_user_with_phone(
                phone, 
                hashed_password, 
                email,
                username
            )
            
            if not user_id:
                return jsonify({"error": "用户创建失败"}), 500
            
            return jsonify({
                "message": "注册成功", 
                "user_id": user_id, 
                "phone": phone
            }), 201
        
        except Exception as e:
            print(f"用户注册失败: {str(e)}")
            return jsonify({"error": f"注册处理失败: {str(e)}"}), 500


    # 用户登录API
    @app.route('/admin/api/user/login', methods=['POST'])
    def admin_api_login():
        """用户登录 API"""
        try:
            data = request.get_json()
            if not data:
                return jsonify({"error": "无效的请求数据"}), 400
                
            phone = data.get('phone')
            code = data.get('code')
            
            if not phone or not code:
                return jsonify({"error": "缺少必要参数"}), 400
            
            manager = get_crawler_config_manager()
            if not manager:
                return jsonify({"error": "数据库连接不可用"}), 500
            
            # 验证码是否有效
            verification = manager.verify_code(phone, code, "login")
            if not verification:
                return jsonify({"error": "验证码无效或已过期"}), 401
                
            # 验证用户
            user = manager.get_admin_user_by_phone(phone)
            if not user:
                return jsonify({"error": "用户不存在"}), 401
            
            # 标记验证码为已使用
            manager.mark_code_as_used(phone, code, "login")
            
            # 创建JWT令牌
            # 注意: 这里使用了简单的session而不是JWT，实际项目中可能需要使用JWT
            session['admin_logged_in'] = True
            session['admin_id'] = user['id']
            session['admin_username'] = user.get('username', phone)
            session['admin_phone'] = phone
            
            # 创建响应
            response_data = {
                "message": "登录成功", 
                "user_id": user['id'], 
                "phone": phone
            }
            
            if user.get("username"):
                response_data["username"] = user["username"]
            
            resp = make_response(jsonify(response_data))
            
            # 设置cookie (可选，主要用于前端检测登录状态)
            resp.set_cookie('logged_in', 'true', max_age=1209600, samesite='Lax')  # 14 days
            
            return resp
        
        except Exception as e:
            print(f"登录失败: {str(e)}")
            return jsonify({"error": f"登录处理失败: {str(e)}"}), 500


    # 用户登出API
    @app.route('/admin/api/user/logout', methods=['POST'])
    def admin_api_logout():
        """用户登出 API"""
        session.pop('admin_logged_in', None)
        session.pop('admin_id', None)
        session.pop('admin_username', None)
        session.pop('admin_phone', None)
        
        resp = make_response(jsonify({"message": "登出成功"}))
        resp.delete_cookie('logged_in')
        
        return resp
    
    # 初始化定时爬虫任务（创建函数但不在这里调用，后面会直接调用）
    def init_scheduled_crawler():
        """初始化并启动定时爬虫任务"""
        def start_crawler_scheduler():
            try:
                # 创建事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # 初始化定时爬虫
                from src.tools.crawler.scheduled_crawler import ScheduledCrawler
                crawler = ScheduledCrawler()
                
                # 加载并调度任务
                async def init_tasks():
                    # 启动调度器
                    crawler.scheduler.start()
                    logger.info("定时爬虫调度器已启动")
                    
                    # 加载数据库中的任务
                    loaded = await crawler.load_and_schedule_tasks()
                    if loaded:
                        logger.info("成功加载定时爬虫任务")
                    else:
                        logger.warning("没有找到活跃的定时爬虫任务")
                
                # 运行初始化
                loop.run_until_complete(init_tasks())
                
                # 保持事件循环运行
                loop.run_forever()
            except Exception as e:
                logger.error(f"初始化定时爬虫任务失败: {str(e)}")
        
        # 在后台线程中启动定时任务
        scheduler_thread = threading.Thread(target=start_crawler_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info("定时爬虫后台线程已启动")
    
    return app, init_scheduled_crawler  # 返回应用和初始化函数

# =============== 应用入口 ===============
if __name__ == "__main__":
    try:
        # 创建应用
        app, init_crawler = create_app()
        
        # 初始化定时爬虫（在后台线程中）
        init_crawler()
        
        # 启动Web服务
        print(f"\n✨ 管理后台已启动！请访问: http://127.0.0.1:5000 \n")
        app.run(debug=True, host='0.0.0.0', port=5000)
        
    except Exception as e:
        print(f"❌ 启动管理后台失败: {str(e)}")
        import traceback
        traceback.print_exc()
