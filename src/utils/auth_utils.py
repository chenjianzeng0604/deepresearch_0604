from functools import wraps
from flask import session, redirect, url_for, render_template, request, flash

def login_required(f):
    """
    检查用户是否已登录的装饰器
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session or not session['admin_logged_in']:
            return redirect(url_for('admin.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def db_required(get_config_manager_func):
    """
    检查数据库连接是否可用的装饰器
    
    Args:
        get_config_manager_func: 获取配置管理器的函数
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            manager = get_config_manager_func()
            if manager is None:
                flash('数据库连接不可用，请检查MySQL配置', 'danger')
                return render_template('error.html', 
                                     message='数据库连接不可用',
                                     details='请确保MySQL服务正在运行，并且环境变量已正确设置')
            return f(*args, **kwargs)
        return decorated_function
    return decorator
